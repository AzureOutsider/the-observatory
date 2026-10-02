using System.Diagnostics;
using System.Net.Http;
using System.Net.NetworkInformation;
using System.Net;
using System.Windows.Forms;

namespace FinanceLauncher;

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        ApplicationConfiguration.Initialize();

        using var mutex = new Mutex(true, @"Local\FinanceOSLauncher", out var createdNew);
        if (!createdNew)
        {
            OpenWebsite();
            return;
        }

        var root = ResolveRoot(args);
        using var launcher = new LauncherContext(root);
        if (launcher.Ready)
        {
            Application.Run(launcher);
        }
    }

    private static string ResolveRoot(string[] args)
    {
        for (var index = 0; index < args.Length - 1; index++)
        {
            if (args[index].Equals("--root", StringComparison.OrdinalIgnoreCase))
            {
                return Path.GetFullPath(args[index + 1]);
            }
        }

        var configuredRoot = Environment.GetEnvironmentVariable("FINANCE_ROOT");
        if (!string.IsNullOrWhiteSpace(configuredRoot))
        {
            return Path.GetFullPath(configuredRoot);
        }

        return FindRepositoryRoot() ?? AppContext.BaseDirectory;
    }

    /// <summary>Walk up from the executable until the repository root (backend/app/main.py) is found.</summary>
    private static string? FindRepositoryRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current != null)
        {
            if (File.Exists(Path.Combine(current.FullName, "backend", "app", "main.py")))
            {
                return current.FullName;
            }
            current = current.Parent;
        }
        return null;
    }

    internal static void OpenWebsite()
    {
        try
        {
            Process.Start(new ProcessStartInfo("http://127.0.0.1:5173")
            {
                UseShellExecute = true,
            });
        }
        catch
        {
            // The existing launcher instance may still be starting.
        }
    }
}

internal sealed class LauncherContext : ApplicationContext
{
    private const string BackendHealthUrl = "http://127.0.0.1:8000/api/health";
    private const string FrontendUrl = "http://127.0.0.1:5173";
    private readonly string _root;
    private readonly string _backendDirectory;
    private readonly string _frontendDirectory;
    private readonly string _logDirectory;
    private readonly string _shutdownToken = Guid.NewGuid().ToString("N");
    private readonly string _shutdownEventName;
    private readonly EventWaitHandle _shutdownEvent;
    private readonly System.Windows.Forms.Timer _timer;
    private readonly NotifyIcon _notifyIcon;
    private readonly object _logLock = new();
    private StreamWriter? _backendLog;
    private StreamWriter? _frontendLog;
    private Process? _backendProcess;
    private Process? _frontendProcess;
    private bool _stopping;

    internal bool Ready { get; }

    internal LauncherContext(string root)
    {
        _root = root;
        _backendDirectory = Path.Combine(_root, "backend");
        _frontendDirectory = Path.Combine(_root, "frontend");
        _logDirectory = Path.Combine(_root, "logs");
        _shutdownEventName = $@"Local\FinanceOS.Shutdown.{Environment.ProcessId}.{Guid.NewGuid():N}";
        _shutdownEvent = new EventWaitHandle(false, EventResetMode.AutoReset, _shutdownEventName);
        _timer = new System.Windows.Forms.Timer { Interval = 500 };
        _timer.Tick += OnTimerTick;
        _notifyIcon = new NotifyIcon
        {
            Icon = SystemIcons.Application,
            Text = "The Observatory",
            Visible = false,
            ContextMenuStrip = CreateMenu(),
        };

        while (true)
        {
            try
            {
                StartServices();
                Ready = true;
                _notifyIcon.Visible = true;
                _notifyIcon.ShowBalloonTip(2500, "The Observatory", "观象台已启动，可从浏览器使用", ToolTipIcon.Info);
                _timer.Start();
                Program.OpenWebsite();
                break;
            }
            catch (Exception error)
            {
                StopServices();
                var retry = MessageBox.Show(
                    $"Finance 网站启动失败。\n\n{error.Message}\n\n可先处理占用端口或查看日志，再点击“重试”。\n日志位置：{_logDirectory}",
                    "The Observatory",
                    MessageBoxButtons.RetryCancel,
                    MessageBoxIcon.Error);
                if (retry != DialogResult.Retry)
                {
                    _notifyIcon.Dispose();
                    _shutdownEvent.Dispose();
                    break;
                }
            }
        }
    }

    private ContextMenuStrip CreateMenu()
    {
        var menu = new ContextMenuStrip();
        var openItem = new ToolStripMenuItem("打开 Finance 网站");
        openItem.Click += (_, _) => Program.OpenWebsite();
        var exitItem = new ToolStripMenuItem("退出观象台");
        exitItem.Click += (_, _) => RequestExit();
        menu.Items.Add(openItem);
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add(exitItem);
        return menu;
    }

    private void StartServices()
    {
        if (!Directory.Exists(Path.Combine(_backendDirectory, "app")) ||
            !File.Exists(Path.Combine(_frontendDirectory, "package.json")))
        {
            throw new InvalidOperationException($"未找到 Finance 项目目录：{_root}");
        }

        if (CanReach(BackendHealthUrl) || CanReach(FrontendUrl))
        {
            throw new InvalidOperationException("检测到网站服务已经在运行。请先打开现有网站，或关闭旧的启动终端后再重试。 ");
        }

        if (IsTcpPortInUse(8000))
        {
            throw new InvalidOperationException("后端端口 8000 已被其他程序占用，后端无法启动。请关闭占用该端口的程序，或在 PowerShell 执行：Get-NetTCPConnection -LocalPort 8000，然后点击“重试”。");
        }

        if (IsTcpPortInUse(5173))
        {
            throw new InvalidOperationException("前端端口 5173 已被其他程序占用，前端无法启动。请关闭占用该端口的程序，或在 PowerShell 执行：Get-NetTCPConnection -LocalPort 5173，然后点击“重试”。");
        }

        Directory.CreateDirectory(_logDirectory);
        _backendLog = OpenLog("backend");
        _frontendLog = OpenLog("frontend");
        var environment = new Dictionary<string, string>
        {
            ["FINANCE_SHUTDOWN_TOKEN"] = _shutdownToken,
            ["FINANCE_SHUTDOWN_EVENT"] = _shutdownEventName,
            ["PYTHONUNBUFFERED"] = "1",
        };

        var virtualEnvPython = Path.Combine(_backendDirectory, ".venv", "Scripts", "python.exe");
        var pythonExecutable = File.Exists(virtualEnvPython) ? virtualEnvPython : "python.exe";
        _backendProcess = StartProcess(
            pythonExecutable,
            _backendDirectory,
            ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
            _backendLog,
            environment);
        _frontendProcess = StartProcess(
            Path.Combine(Environment.SystemDirectory, "cmd.exe"),
            _frontendDirectory,
            ["/d", "/s", "/c", "npm run dev -- --host 127.0.0.1 --port 5173 --strictPort"],
            _frontendLog,
            environment);

        var waitFailure = WaitForServices(TimeSpan.FromSeconds(45));
        if (waitFailure is not null)
        {
            throw new InvalidOperationException(waitFailure);
        }
    }

    private Process StartProcess(
        string fileName,
        string workingDirectory,
        IEnumerable<string> arguments,
        StreamWriter log,
        IReadOnlyDictionary<string, string> environment)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = fileName,
            WorkingDirectory = workingDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        foreach (var argument in arguments)
        {
            startInfo.ArgumentList.Add(argument);
        }
        foreach (var pair in environment)
        {
            startInfo.Environment[pair.Key] = pair.Value;
        }

        var process = new Process { StartInfo = startInfo, EnableRaisingEvents = true };
        process.OutputDataReceived += (_, eventArgs) => WriteLog(log, eventArgs.Data);
        process.ErrorDataReceived += (_, eventArgs) => WriteLog(log, eventArgs.Data);
        process.Start();
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();
        return process;
    }

    private string? WaitForServices(TimeSpan timeout)
    {
        var deadline = DateTime.UtcNow + timeout;
        using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };
        while (DateTime.UtcNow < deadline)
        {
            if (_backendProcess?.HasExited == true)
            {
                return $"后端进程启动后立即退出（退出码 {GetExitCode(_backendProcess)}）。这通常表示 Python 依赖、配置或端口存在问题，请查看 logs\\backend.log，然后点击“重试”。";
            }

            if (_frontendProcess?.HasExited == true)
            {
                return $"前端进程启动后立即退出（退出码 {GetExitCode(_frontendProcess)}）。这通常表示 Node/npm 依赖或端口存在问题，请查看 logs\\frontend.log，然后点击“重试”。";
            }

            if (CanReach(BackendHealthUrl, client) && CanReach(FrontendUrl, client))
            {
                return null;
            }

            Thread.Sleep(500);
        }
        var backendReady = CanReach(BackendHealthUrl, client);
        var frontendReady = CanReach(FrontendUrl, client);
        if (!backendReady && !frontendReady)
        {
            return "后端和前端都未在 45 秒内准备完成，请查看 logs\\backend.log 与 logs\\frontend.log。可处理日志中的首个错误后点击“重试”。";
        }

        return backendReady
            ? "后端已启动，但前端未在 45 秒内准备完成，请查看 logs\\frontend.log 后点击“重试”。"
            : "前端已启动，但后端未在 45 秒内准备完成，请查看 logs\\backend.log 后点击“重试”。";
    }

    private static bool IsTcpPortInUse(int port)
    {
        return IPGlobalProperties.GetIPGlobalProperties()
            .GetActiveTcpListeners()
            .Any(endpoint => endpoint.Port == port && (IPAddress.IsLoopback(endpoint.Address) || endpoint.Address.Equals(IPAddress.Any)));
    }

    private static int GetExitCode(Process process)
    {
        try { return process.ExitCode; }
        catch { return -1; }
    }

    private static bool CanReach(string url, HttpClient? client = null)
    {
        try
        {
            using var localClient = client is null ? new HttpClient { Timeout = TimeSpan.FromSeconds(1) } : null;
            var activeClient = client ?? localClient!;
            using var response = activeClient.GetAsync(url).GetAwaiter().GetResult();
            return response.IsSuccessStatusCode;
        }
        catch
        {
            return false;
        }
    }

    private StreamWriter OpenLog(string name)
    {
        var path = Path.Combine(_logDirectory, $"{name}.log");
        return new StreamWriter(new FileStream(path, FileMode.Append, FileAccess.Write, FileShare.ReadWrite))
        {
            AutoFlush = true,
        };
    }

    private void WriteLog(StreamWriter log, string? line)
    {
        if (line is null) return;
        lock (_logLock)
        {
            log.WriteLine($"[{DateTime.Now:yyyy-MM-dd HH:mm:ss}] {line}");
        }
    }

    private void OnTimerTick(object? sender, EventArgs eventArgs)
    {
        if (_shutdownEvent.WaitOne(0))
        {
            RequestExit();
            return;
        }

        if (!_stopping && ((_backendProcess?.HasExited ?? false) || (_frontendProcess?.HasExited ?? false)))
        {
            var backendStopped = _backendProcess?.HasExited == true;
            var frontendStopped = _frontendProcess?.HasExited == true;
            var service = backendStopped && frontendStopped ? "后端和前端" : backendStopped ? "后端" : "前端";
            var process = backendStopped ? _backendProcess : _frontendProcess;
            var exitCode = process is null ? -1 : GetExitCode(process);
            _notifyIcon.ShowBalloonTip(4500, "The Observatory", $"{service}服务已意外停止（退出码 {exitCode}），启动器将停止剩余服务。请查看 logs 目录后重新启动。", ToolTipIcon.Warning);
            RequestExit();
        }
    }

    private void RequestExit()
    {
        if (_stopping) return;
        _stopping = true;
        _timer.Stop();
        StopServices();
        _notifyIcon.Visible = false;
        _notifyIcon.Dispose();
        _shutdownEvent.Dispose();
        ExitThread();
    }

    private void StopServices()
    {
        KillProcessTree(_frontendProcess);
        KillProcessTree(_backendProcess);
        _frontendProcess = null;
        _backendProcess = null;
        _frontendLog?.Dispose();
        _backendLog?.Dispose();
        _frontendLog = null;
        _backendLog = null;
    }

    private static void KillProcessTree(Process? process)
    {
        if (process is null) return;
        try
        {
            if (!process.HasExited)
            {
                process.Kill(entireProcessTree: true);
                process.WaitForExit(5000);
            }
        }
        catch
        {
            // The process may have exited between the checks.
        }
        finally
        {
            process.Dispose();
        }
    }
}
