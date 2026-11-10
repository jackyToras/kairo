import { useState } from "react";
import { KeyRound, Sparkles, X } from "lucide-react";
import { ConfigResponse, RuntimeProviderOverride } from "../types";

interface ProviderModalProps {
  open: boolean;
  config: ConfigResponse | null;
  currentOverride: RuntimeProviderOverride | null;
  onSave: (override: RuntimeProviderOverride | null) => void;
  onClose: () => void;
}

export function ProviderModal({
  open,
  config,
  currentOverride,
  onSave,
  onClose,
}: ProviderModalProps) {
  const [provider, setProvider] = useState(
    currentOverride?.provider || config?.active_provider || "ollama"
  );
  const [model, setModel] = useState(
    currentOverride?.model || config?.active_model || "mistral:latest"
  );
  const [apiKey, setApiKey] = useState(currentOverride?.apiKey || "");

  if (!open || !config) return null;

  const selectedPreset = config.presets.find((p) => p.id === provider);
  const hasEnvKey = Boolean(config.configured_keys[provider]);

  const handleSelectPreset = (id: string) => {
    setProvider(id);
    const preset = config.presets.find((p) => p.id === id);
    if (preset) setModel(preset.default_model);
  };

  const handleApply = () => {
    onSave({ provider, model: model.trim(), apiKey: apiKey.trim() });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="w-full max-w-md rounded-xl border border-zinc-800 bg-zinc-950 shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-emerald-400" />
            <h3 className="text-sm font-semibold text-zinc-100">Free-Tier LLM Provider</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 text-zinc-400 hover:text-zinc-100 rounded hover:bg-zinc-800"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-4 space-y-4 text-xs">
          <div className="space-y-2">
            {config.presets.map((preset) => (
              <button
                key={preset.id}
                type="button"
                onClick={() => handleSelectPreset(preset.id)}
                className={`w-full text-left rounded-lg border p-3 transition-colors ${
                  provider === preset.id
                    ? "border-emerald-500/70 bg-emerald-500/10"
                    : "border-zinc-800 bg-zinc-900/50 hover:border-zinc-700"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-zinc-100">{preset.label}</span>
                  <span className="px-1.5 py-0.5 rounded bg-zinc-800 text-emerald-300 font-mono text-[10px]">
                    {preset.cost}
                  </span>
                </div>
                <p className="text-zinc-400 mt-1">{preset.notes}</p>
              </button>
            ))}
          </div>

          <div className="space-y-1.5">
            <label className="block text-zinc-400 font-medium">Model Name</label>
            <input
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-100 font-mono text-xs focus:outline-none focus:border-emerald-500/60"
            />
          </div>

          {selectedPreset?.requires_key && (
            <div className="space-y-1.5">
              <label className="flex items-center justify-between text-zinc-400 font-medium">
                <span className="flex items-center gap-1">
                  <KeyRound className="w-3.5 h-3.5" /> API Key (in-memory only)
                </span>
                {hasEnvKey && <span className="text-emerald-400">Configured in .env</span>}
              </label>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={hasEnvKey ? "Using .env key (or paste override)" : "Paste free-tier API key"}
                className="w-full px-3 py-2 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-100 font-mono text-xs focus:outline-none focus:border-emerald-500/60"
              />
            </div>
          )}

          <div className="flex items-center justify-between pt-2 border-t border-zinc-800">
            <button
              type="button"
              onClick={() => {
                onSave(null);
                onClose();
              }}
              className="px-3 py-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900"
            >
              Reset to Default
            </button>
            <button
              type="button"
              onClick={handleApply}
              className="px-4 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-semibold"
            >
              Apply Provider
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
