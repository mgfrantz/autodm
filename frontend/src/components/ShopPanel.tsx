import { useEffect, useState } from 'react'
import {
  getShopOverview,
  getMerchant,
  buyFromMerchant,
  sellToMerchant,
} from '../stores/api'
import type {
  ShopOverview,
  ShopMerchant,
  ShopTransactionResult,
  ShopStockEntry,
  ShopSellEntry,
} from '../types'

const titleCase = (s: string) =>
  s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

const RARITY_COLOR: Record<string, string> = {
  common: 'text-parchment-300',
  uncommon: 'text-leaf-300',
  rare: 'text-arcane-300',
  very_rare: 'text-purple-300',
  legendary: 'text-gold-300',
}

interface Props {
  gameId: number
  onGoldChange?: (gold: number) => void
}

export default function ShopPanel({ gameId, onGoldChange }: Props) {
  const [overview, setOverview] = useState<ShopOverview | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [merchant, setMerchant] = useState<ShopMerchant | null>(null)
  const [gold, setGold] = useState(0)
  const [tab, setTab] = useState<'buy' | 'sell'>('buy')
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const loadOverview = async () => {
    setLoading(true)
    setError(null)
    try {
      const ov = await getShopOverview(gameId)
      setOverview(ov)
      setGold(ov.gold)
      onGoldChange?.(ov.gold)
    } catch {
      setError('Failed to load the market')
    }
    setLoading(false)
  }

  useEffect(() => {
    loadOverview()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gameId])

  const openMerchant = async (merchantType: string) => {
    setSelected(merchantType)
    setMerchant(null)
    setFeedback(null)
    setTab('buy')
    try {
      const m = await getMerchant(gameId, merchantType)
      setMerchant(m)
      // Refresh overview so "visited" reflects reality
      const ov = await getShopOverview(gameId)
      setOverview(ov)
    } catch {
      setError('Failed to reach this merchant')
    }
  }

  const notifyGold = (g: number) => {
    setGold(g)
    onGoldChange?.(g)
  }

  const handleBuy = async (line: ShopStockEntry, qty = 1) => {
    if (busy) return
    setBusy(true)
    setFeedback(null)
    try {
      const res: ShopTransactionResult = await buyFromMerchant(gameId, selected!, line.item.id, qty)
      if (res.success) {
        notifyGold(res.gold)
        setFeedback(`✓ ${res.message}`)
        // Refresh merchant stock + player inventory
        const m = await getMerchant(gameId, selected!)
        setMerchant(m)
      } else {
        setFeedback(`✗ ${res.message}`)
      }
    } catch {
      setError('Purchase failed')
    }
    setBusy(false)
  }

  const handleSell = async (line: ShopSellEntry, qty = 1) => {
    if (busy) return
    setBusy(true)
    setFeedback(null)
    try {
      const res: ShopTransactionResult = await sellToMerchant(gameId, selected!, line.item.id, qty)
      if (res.success) {
        notifyGold(res.gold)
        setFeedback(`✓ ${res.message}`)
        const m = await getMerchant(gameId, selected!)
        setMerchant(m)
      } else {
        setFeedback(`✗ ${res.message}`)
      }
    } catch {
      setError('Sale failed')
    }
    setBusy(false)
  }

  if (loading) {
    return <div className="text-parchment-400 animate-pulse text-center py-12">Wandering the market…</div>
  }
  if (error || !overview) {
    return (
      <div className="text-center py-8">
        <div className="text-blood-400 mb-3">{error || 'No market data'}</div>
        <button className="btn-primary" onClick={loadOverview}>Retry</button>
      </div>
    )
  }

  // --- Merchant picker ---------------------------------------------------- #
  if (!selected) {
    return (
      <div>
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs uppercase tracking-wide text-parchment-500">
            {titleCase(overview.settlement_tier)} market
          </span>
          <span className="font-fantasy text-gold-300">🪙 {gold} gp</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {overview.merchants.map((m) => (
            <button
              key={m.merchant_type}
              onClick={() => openMerchant(m.merchant_type)}
              className="text-left rounded-lg p-3 bg-parchment-900/60 hover:bg-parchment-800/60 transition-all duration-150 hover:-translate-y-0.5 active:scale-95 border border-parchment-800/40"
            >
              <div className="flex items-center justify-between">
                <span className="font-fantasy text-parchment-200">{m.label}</span>
                {m.visited && <span className="text-[10px] text-leaf-400">● visited</span>}
              </div>
              <div className="text-xs text-parchment-500 mt-1">{m.description}</div>
            </button>
          ))}
        </div>
      </div>
    )
  }

  // --- Merchant view ----------------------------------------------------- #
  if (!merchant) {
    return <div className="text-parchment-400 animate-pulse text-center py-12">Approaching the {selected}…</div>
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <button
          className="text-parchment-400 hover:text-parchment-200 text-sm"
          onClick={() => { setSelected(null); setMerchant(null); setFeedback(null) }}
        >
          ← Merchants
        </button>
        <span className="font-fantasy text-gold-300">🪙 {gold} gp</span>
      </div>

      <div className="mb-3">
        <h3 className="font-fantasy text-lg text-parchment-200">{merchant.name}</h3>
        <div className="text-xs text-parchment-500">
          {merchant.label} · {titleCase(merchant.settlement_tier)} · purse: {merchant.gold} gp
        </div>
      </div>

      {/* Buy / Sell tabs */}
      <div className="flex gap-2 mb-3">
        <button
          onClick={() => setTab('buy')}
          className={`flex-1 text-sm py-1.5 rounded transition-colors ${
            tab === 'buy' ? 'bg-arcane-700 text-parchment-100' : 'bg-parchment-800/60 text-parchment-400 hover:bg-parchment-700/60'
          }`}
        >
          🛒 Buy
        </button>
        <button
          onClick={() => setTab('sell')}
          className={`flex-1 text-sm py-1.5 rounded transition-colors ${
            tab === 'sell' ? 'bg-leaf-700 text-parchment-100' : 'bg-parchment-800/60 text-parchment-400 hover:bg-parchment-700/60'
          }`}
        >
          💰 Sell
        </button>
      </div>

      {/* Buy list */}
      {tab === 'buy' && (
        <div className="space-y-1.5 mb-3 max-h-[40vh] overflow-y-auto pr-1">
          {merchant.stock.length === 0 && (
            <div className="text-center text-parchment-500 text-sm py-6">Sold out. Try restocking.</div>
          )}
          {merchant.stock.map((line) => {
            const afford = gold >= line.buy_price
            return (
              <div
                key={line.item.id}
                className="flex items-center justify-between rounded-md px-2.5 py-2 bg-parchment-900/60"
              >
                <div className="min-w-0">
                  <div className={`text-sm truncate ${RARITY_COLOR[line.item.rarity] ?? 'text-parchment-200'}`}>
                    {line.item.name}
                    {line.quantity > 1 && <span className="text-parchment-600 text-xs"> ×{line.quantity}</span>}
                  </div>
                  <div className="text-[11px] text-parchment-500 truncate">
                    {line.item.damage_dice_count ? `${line.item.damage_dice_count}d${line.item.damage_dice_sides} ${line.item.damage_type ?? ''} · ` : ''}
                    {line.buy_price} gp
                  </div>
                </div>
                <button
                  className="btn-primary text-xs px-3 py-1 shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
                  disabled={!afford || busy}
                  onClick={() => handleBuy(line, 1)}
                  title={afford ? `Buy ${line.item.name}` : 'Not enough gold'}
                >
                  Buy
                </button>
              </div>
            )
          })}
        </div>
      )}

      {/* Sell list */}
      {tab === 'sell' && (() => {
        const sellables = merchant.player_inventory ?? []
        return (
        <div className="space-y-1.5 mb-3 max-h-[40vh] overflow-y-auto pr-1">
          {sellables.length === 0 && (
            <div className="text-center text-parchment-500 text-sm py-6">Your pack is empty.</div>
          )}
          {sellables.map((line) => {
            return (
              <div
                key={line.item.id}
                className={`flex items-center justify-between rounded-md px-2.5 py-2 bg-parchment-900/60 ${
                  !line.merchant_buys ? 'opacity-50' : ''
                }`}
              >
                <div className="min-w-0">
                  <div className={`text-sm truncate ${RARITY_COLOR[line.item.rarity] ?? 'text-parchment-200'}`}>
                    {line.item.name}
                    {line.quantity > 1 && <span className="text-parchment-600 text-xs"> ×{line.quantity}</span>}
                    {line.equipped && <span className="text-[10px] text-gold-400 ml-1">(equipped)</span>}
                  </div>
                  <div className="text-[11px] text-parchment-500 truncate">
                    {line.merchant_buys ? `${line.sell_price} gp each` : `${merchant.name} doesn't buy this`}
                  </div>
                </div>
                <button
                  className="btn-primary text-xs px-3 py-1 shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
                  disabled={!line.merchant_buys || busy}
                  onClick={() => handleSell(line, 1)}
                >
                  Sell
                </button>
              </div>
            )
          })}
        </div>
        )
      })()}

      {/* Feedback */}
      {feedback && (
        <div className="rounded-lg p-2.5 text-sm bg-parchment-900/70 border border-parchment-800/50 animate-scale-in">
          {feedback}
        </div>
      )}
    </div>
  )
}
