import { FormEvent, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Check, X } from "lucide-react";
import { toast } from "sonner";
import { Holding } from "../api/client";
import { HoldingUpdatePayload, useUpdateHolding } from "../hooks/useHoldings";

type Props = {
  holding: Holding;
  onClose: () => void;
  onSaved: (holding: Holding) => void;
};

export function HoldingEditor({ holding, onClose, onSaved }: Props) {
  const [customName, setCustomName] = useState(holding.asset.custom_name ?? holding.asset.name);
  const [amount, setAmount] = useState(holding.amount);
  const [profit, setProfit] = useState(holding.profit ?? "");
  const [units, setUnits] = useState(holding.units ?? "");
  const [costBasis, setCostBasis] = useState(holding.cost_basis ?? "");
  const [correctionReason, setCorrectionReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const updateHolding = useUpdateHolding();
  const saving = updateHolding.isPending;
  const snapshotChanged = amount !== holding.amount || profit !== (holding.profit ?? "") || units !== (holding.units ?? "") || costBasis !== (holding.cost_basis ?? "");

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !saving) onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, saving]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!amount.trim()) {
      setError("请填写当前金额");
      return;
    }
    if (snapshotChanged && !correctionReason.trim()) {
      setError("请填写本次修正原因，便于后续追溯");
      return;
    }
    setError(null);
    const payload: HoldingUpdatePayload = {};
    if (customName.trim() !== (holding.asset.custom_name ?? holding.asset.name)) payload.custom_name = customName.trim() || null;
    if (amount !== holding.amount) payload.amount = amount.trim();
    if (profit !== (holding.profit ?? "")) payload.profit = profit.trim() || null;
    if (units !== (holding.units ?? "")) payload.units = units.trim() || null;
    if (costBasis !== (holding.cost_basis ?? "")) payload.cost_basis = costBasis.trim() || null;
    if (snapshotChanged) payload.correction_reason = correctionReason.trim();
    if (Object.keys(payload).length === 0) {
      setError("请先修改名称或持仓数据");
      return;
    }
    try {
      const updated = await updateHolding.mutateAsync({
        id: holding.id,
        payload,
      });
      onSaved(updated);
      toast.success("持仓修正已保存", { className: "holdingToast" });
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : "保存失败，请稍后重试";
      setError(message);
      toast.error(message, { className: "holdingToast" });
    }
  }

  // Glass/animated containers establish a containing block for fixed children.
  // Render outside them so the correction dialog is anchored to the viewport.
  return createPortal(
    <div className="holdingEditorBackdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && !saving && onClose()}>
      <form className="holdingEditor" onSubmit={submit} role="dialog" aria-modal="true" aria-labelledby="holding-editor-title">
        <div className="holdingEditorHeader">
          <div>
            <span className="kicker">POSITION CORRECTION</span>
            <h2 id="holding-editor-title">修正当前持仓</h2>
            <p>{holding.asset.custom_name || holding.asset.name} · {holding.asset.code}</p>
          </div>
          <button className="modalCloseButton" type="button" onClick={onClose} disabled={saving} aria-label="关闭">
            <X size={17} />
          </button>
        </div>
        <div className="holdingEditorNotice">可修改显示名称；留空恢复行情名称。只改名称不会改变持仓成本。修正金额、份额等数据时请填写原因，不会新增交易流水。</div>
        <div className="holdingEditorGrid">
          <label className="holdingEditorReason"><span>标的名称</span><input name="custom_name" value={customName} onChange={(event) => setCustomName(event.target.value)} maxLength={255} placeholder={holding.asset.name} autoFocus /></label>
          <label><span>当前金额（必填）</span><input name="amount" value={amount} onChange={(event) => setAmount(event.target.value)} type="number" min="0" step="0.01" inputMode="decimal" /></label>
          <label><span>当前盈亏</span><input value={profit} onChange={(event) => setProfit(event.target.value)} type="number" step="0.01" inputMode="decimal" placeholder="可留空" /></label>
          <label><span>持有份额</span><input value={units} onChange={(event) => setUnits(event.target.value)} type="number" min="0" step="0.01" inputMode="decimal" placeholder="最多两位小数，可留空" /></label>
          <label><span>成本金额</span><input value={costBasis} onChange={(event) => setCostBasis(event.target.value)} type="number" min="0" step="0.01" inputMode="decimal" placeholder="可留空" /></label>
          <label className="holdingEditorReason"><span>本次修正原因{snapshotChanged ? "（必填）" : "（修改持仓数据时必填）"}</span><textarea value={correctionReason} onChange={(event) => setCorrectionReason(event.target.value)} maxLength={500} placeholder="例如：已与支付宝持仓对账" /></label>
        </div>
        {error && <div className="notice holdingEditorError">{error}</div>}
        <div className="holdingEditorActions">
          <button className="iconButton" type="button" onClick={onClose} disabled={saving}>取消</button>
          <button className="primaryButton" type="submit" disabled={saving}><Check size={15} />{saving ? "保存中…" : "保存修正"}</button>
        </div>
      </form>
    </div>,
    document.body,
  );
}
