/**
 * SubclassPanel — DnD 5e subclass (archetype) console.
 *
 * Lets the player see their current subclass, the merged class+subclass feature
 * timeline, and — when eligible and not yet chosen — pick a subclass (a
 * permanent choice). Mirrors the feats/exhaustion panel patterns.
 */
import { useCallback, useEffect, useState } from 'react';
import type {
  CharacterSubclassResponse,
  SubclassInfo,
} from '../types';
import {
  getCharacterSubclass,
  getAvailableSubclasses,
  chooseSubclass,
} from '../stores/api';

interface SubclassPanelProps {
  characterId: number;
  onChanged?: () => void | Promise<void>;
}

export default function SubclassPanel({ characterId, onChanged }: SubclassPanelProps) {
  const [state, setState] = useState<CharacterSubclassResponse | null>(null);
  const [available, setAvailable] = useState<SubclassInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sub, avail] = await Promise.all([
        getCharacterSubclass(characterId),
        getAvailableSubclasses(characterId),
      ]);
      setState(sub);
      setAvailable(avail.available);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to load subclass data';
      // Axios errors carry a response detail.
      const anyErr = e as { response?: { data?: { detail?: string } } };
      setError(anyErr.response?.data?.detail ?? msg);
    } finally {
      setLoading(false);
    }
  }, [characterId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleChoose = async (subclassId: string, className?: string) => {
    setBusy(true);
    setError(null);
    setFlash(null);
    try {
      const result = await chooseSubclass(characterId, subclassId, className);
      setFlash(`✦ ${result.message}`);
      await refresh();
      if (onChanged) await onChanged();
    } catch (e: unknown) {
      const anyErr = e as { response?: { data?: { detail?: string } }; message?: string };
      setError(anyErr.response?.data?.detail ?? anyErr.message ?? 'Failed to choose subclass');
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="text-parchment-400 text-sm py-8 text-center">
        Loading subclass data…
      </div>
    );
  }

  if (error && !state) {
    return (
      <div className="text-blood-300 text-sm py-4 text-center">
        <p>{error}</p>
        <button className="btn-primary mt-3 text-sm px-3 py-1.5" onClick={refresh}>
          Retry
        </button>
      </div>
    );
  }

  const pending = state?.pending ?? [];
  const hasPending = pending.length > 0;
  const choices = state?.choices ?? [];

  return (
    <div className="space-y-5">
      {error && (
        <div className="text-blood-300 text-xs bg-blood-900/30 border border-blood-700/40 rounded px-3 py-2">
          {error}
        </div>
      )}
      {flash && (
        <div className="text-arcane-200 text-sm bg-arcane-900/30 border border-arcane-700/40 rounded px-3 py-2 animate-fade-in">
          {flash}
        </div>
      )}

      {/* DM summary line */}
      {state && (
        <div className="text-xs text-parchment-400 bg-parchment-900/40 border border-parchment-800/50 rounded px-3 py-2">
          <span className="text-parchment-300 font-semibold">DM context: </span>
          {state.dm_summary}
        </div>
      )}

      {/* Current subclass choices */}
      {choices.length > 0 ? (
        <section className="space-y-3">
          <h3 className="font-fantasy text-lg text-gold-300">Current Archetype</h3>
          {choices.map((c) => (
            <div
              key={c.subclass_id}
              className="border border-arcane-700/40 bg-arcane-900/20 rounded-md p-3"
            >
              <div className="flex items-baseline justify-between">
                <span className="font-fantasy text-arcane-100 text-lg">{c.name}</span>
                <span className="text-xs text-parchment-400 uppercase tracking-wide">
                  {c.category} · {c.class_name}
                </span>
              </div>
              {c.features.length > 0 ? (
                <ul className="mt-2 space-y-1.5">
                  {c.features.map((f, i) => (
                    <li key={i} className="text-sm text-parchment-200 flex gap-2">
                      <span className="text-gold-400 font-mono text-xs mt-0.5 shrink-0">
                        Lv {f.level}
                      </span>
                      <span>{f.feature}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-parchment-500 mt-1">
                  No subclass features in effect at this level yet.
                </p>
              )}
            </div>
          ))}
        </section>
      ) : (
        !hasPending && (
          <p className="text-sm text-parchment-400">
            No subclass chosen yet. You'll be able to choose an archetype when you
            reach your class's subclass level.
          </p>
        )
      )}

      {/* Pending choice — show available subclasses */}
      {hasPending && (
        <section className="space-y-3">
          <h3 className="font-fantasy text-lg text-gold-300">Choose Your Path</h3>
          {pending.map((p) => (
            <div key={p.class_name}>
              <p className="text-sm text-parchment-300 mb-2">
                Your <span className="capitalize text-parchment-100">{p.class_name}</span> has
                reached level {p.choice_level} — choose a{' '}
                <span className="text-gold-300">{p.category}</span>:
              </p>
              <div className="grid gap-2">
                {available
                  .filter((s) => s.char_class === p.class_name)
                  .map((s) => (
                    <div
                      key={s.id}
                      className="border border-parchment-800/60 bg-parchment-900/30 rounded-md p-3 hover:border-gold-600/50 transition-colors"
                    >
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="font-fantasy text-parchment-100">{s.name}</span>
                        <span className="text-xs text-parchment-500">
                          {s.features.length} feature{s.features.length === 1 ? '' : 's'}
                        </span>
                      </div>
                      <p className="text-xs text-parchment-400 mt-1 leading-relaxed">
                        {s.description}
                      </p>
                      <ul className="mt-2 space-y-1">
                        {s.features.map((f, i) => (
                          <li key={i} className="text-xs text-parchment-300 flex gap-2">
                            <span className="text-gold-400/80 font-mono shrink-0">
                              Lv {f.level}
                            </span>
                            <span className="line-clamp-2">{f.feature}</span>
                          </li>
                        ))}
                      </ul>
                      <button
                        disabled={busy}
                        onClick={() => handleChoose(s.id, s.char_class)}
                        className="btn-primary mt-3 text-sm px-3 py-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {busy ? 'Choosing…' : `Choose ${s.name}`}
                      </button>
                    </div>
                  ))}
              </div>
            </div>
          ))}
        </section>
      )}

      {/* Feature timeline (class + subclass merged) */}
      {state && state.timeline.length > 0 && (
        <section className="space-y-2">
          <h3 className="font-fantasy text-lg text-gold-300">Feature Timeline</h3>
          <p className="text-xs text-parchment-500">
            Class progression{choices.length > 0 ? ' merged with subclass features' : ''}.
          </p>
          <ul className="space-y-1 max-h-64 overflow-y-auto pr-1">
            {state.timeline.map((entry, i) => (
              <li
                key={i}
                className={`text-sm flex gap-2 px-2 py-1 rounded ${
                  entry.source === 'class'
                    ? 'bg-parchment-900/20'
                    : 'bg-arcane-900/20 border border-arcane-800/30'
                }`}
              >
                <span className="text-gold-400 font-mono text-xs mt-0.5 shrink-0 w-10">
                  Lv {entry.level}
                </span>
                <span className="text-parchment-300">
                  {entry.source !== 'class' && (
                    <span className="text-arcane-300 font-semibold mr-1">
                      {entry.source}:
                    </span>
                  )}
                  {entry.feature}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
