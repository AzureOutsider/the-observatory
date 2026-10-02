import { Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Holding } from "../api/client";

type SearchDialogProps = {
  open: boolean;
  holdings: Holding[];
  onClose: () => void;
  onSelectHolding: (holding: Holding) => void;
};

export function SearchDialog({ open, holdings, onClose, onSelectHolding }: SearchDialogProps) {
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const results = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return holdings.slice(0, 8);
    return holdings.filter((holding) => `${holding.asset.name} ${holding.asset.code} ${holding.asset.official_name ?? ""}`.toLocaleLowerCase().includes(normalized)).slice(0, 8);
  }, [holdings, query]);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    inputRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, open]);

  if (!open) return null;
  return (
    <div className="searchDialogBackdrop" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }}>
      <section className="searchDialog" role="dialog" aria-modal="true" aria-labelledby="search-dialog-title">
        <div className="searchDialogHeader">
          <div><Search size={17} /><h2 id="search-dialog-title">搜索持仓</h2></div>
          <button className="modalCloseButton" type="button" onClick={onClose} title="关闭搜索" aria-label="关闭搜索"><X size={17} /></button>
        </div>
        <label className="searchDialogInput"><Search size={16} /><input ref={inputRef} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索名称或代码" aria-label="搜索名称或代码" /></label>
        <div className="searchDialogResults" role="listbox" aria-label="持仓搜索结果">
          {results.map((holding) => <button key={holding.id} type="button" role="option" onClick={() => onSelectHolding(holding)}><span><strong>{holding.asset.name}</strong><small>{holding.asset.code}</small></span><b>¥{Number(holding.amount).toFixed(2)}</b></button>)}
          {results.length === 0 && <p className="searchDialogEmpty">未找到匹配持仓</p>}
          {results.length > 0 && !query.trim() && <p className="searchDialogHint">输入名称或代码缩小范围</p>}
        </div>
      </section>
    </div>
  );
}
