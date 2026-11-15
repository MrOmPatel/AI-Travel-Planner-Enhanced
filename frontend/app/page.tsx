'use client'
import { useState, useEffect, useCallback } from "react"
import {
  Loader2, Plane, MapPin, Hotel, UtensilsCrossed, Calendar,
  RefreshCw, Thermometer, CloudRain, Sun, Cloud, Wind, Zap,
  Clock, IndianRupee, AlertTriangle, CheckCircle2, PartyPopper,
  RotateCcw, LogIn, LogOut, UserPlus, History, Eye, Trash2,
  ChevronDown, ChevronUp, Lock, Mail, User, Camera, ArrowUpRight,
  Coffee, Compass, Sparkles
} from 'lucide-react'
import { Button }   from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:5000"

// ─── Types ────────────────────────────────────────────────────────────────────
interface AuthUser { token: string; email: string; name: string }

interface TravelDetails {
  destination: string; duration: number; budget_usd: number
  budget_inr: number; inr_rate: number; travelers: number
  travel_type: string; interests: string[]; overview: string
  start_date?: string; end_date?: string
  days_until_trip?: number; season?: string
}
interface Place {
  name: string; description: string; category: string; location: string
  how_to_reach: string; best_time: string; visit_duration_hrs: number
  entry_fee_inr: number; is_outdoor: boolean; open_time: string
  close_time: string; rating: number; tips: string
  image_url: string; maps_link: string; tags: string[]
}
interface Restaurant {
  name: string; cuisine: string; description: string; budget_level: string
  avg_cost_per_person_inr: number; location: string; rating: number
  specialties: string[]; atmosphere: string; best_time: string
  reservation_needed: boolean; image_url: string; maps_link: string
  over_budget_guideline?: boolean
}
interface Hotel {
  name: string; category: string; description: string; location: string
  price_per_night_inr: number; total_estimated_inr: number; rating: number
  amenities: string[]; room_type: string; proximity: string
  booking_tip: string; image_url: string; maps_link: string
  over_budget_guideline?: boolean
}
interface Activity {
  time: string; activity: string; description: string
  location: string; duration: string; cost_inr: number | string
  is_meal?: boolean; meal_type?: string
  travel_note?: string; caution?: string; place_id?: string
}
interface AdditionalPlace {
  name: string; description?: string; location?: string
  reason?: string; schedule_status?: string; image_url?: string; maps_link?: string
}
interface DayPlan {
  day: number; title: string; weather_note: string
  actual_date?: string; date_label?: string
  activities: Activity[]
  meals: { breakfast: unknown; lunch: unknown; dinner: unknown }
  additional_places?: AdditionalPlace[]
  all_place_names?: string[]
  route_warnings?: string[]
  estimated_cost_inr: number | string; tips: string
  has_event: boolean; event_name: string | null
}
interface WeatherDay {
  date: string; condition: string; temp_c: number
  description: string; advice: string; is_outdoor_ok: boolean
}
interface Weather {
  city: string; current_temp_c: number | null; feels_like_c: number | null
  humidity_pct: number | null; condition: string; description: string
  advice: string; is_outdoor_ok: boolean; daily_forecast: WeatherDay[]
  data_available: boolean
  forecast_type?: "live" | "seasonal" | "none"
  seasonal_note?: string; days_until_trip?: number; trip_start_date?: string
}
interface BudgetBreakdown {
  accommodation: number; food: number; activities: number
  transportation: number; miscellaneous: number; total_estimated: number
  user_budget_inr: number; user_budget_usd: number; inr_rate: number
  remaining: number; within_budget: boolean
  envelope?: {
    hotel_max_per_night: number
    meal_budget_per_person: number
    activities_per_day: number
  }
}
interface TravelPlan {
  saved_trip_id?: number
  travel_details: TravelDetails; places: Place[]; restaurants: Restaurant[]
  hotels: Hotel[]; weather: Weather; itinerary: DayPlan[]
  budget_breakdown: BudgetBreakdown
}
interface SavedTrip {
  id: number; destination: string; duration: number
  start_date: string | null; end_date: string | null
  status: "upcoming" | "past"; created_at: string
  travel_details: TravelDetails
  full_plan?: TravelPlan
  overview_data?: {
    places_visited: string[]; total_days: number; destination: string
    budget_inr: number; budget_breakdown: BudgetBreakdown
    highlights: string[]; hotel_stayed: string | null
  }
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
const fmt = (n: number | undefined | null) =>
  n != null ? "₹" + n.toLocaleString("en-IN") : "₹0"

const mealStr = (val: unknown): string => {
  if (!val) return "—"
  if (typeof val === "string") return val
  if (typeof val === "object") {
    const v = val as Record<string, unknown>
    const name = v.restaurant ?? v.name ?? v.place ?? v.venue ?? v.meal ?? ""
    const cost = v.cost_inr ?? v.cost ?? v.price ?? ""
    if (name) return cost ? `${String(name)} (₹${cost})` : String(name)
    return Object.values(v).filter(Boolean).join(" · ")
  }
  return String(val)
}

const StarRow = ({ rating }: { rating: number }) => (
  <span className="text-amber-500 text-sm">
    {"★".repeat(Math.round(rating))}{"☆".repeat(5 - Math.round(rating))} {rating.toFixed(1)}
  </span>
)

const weatherIcon = (cond: string) => {
  const c = cond.toLowerCase()
  if (c.includes("rain") || c.includes("drizzle")) return <CloudRain className="h-4 w-4 text-blue-500" />
  if (c.includes("storm")) return <Zap className="h-4 w-4 text-yellow-600" />
  if (c.includes("cloud")) return <Cloud className="h-4 w-4 text-gray-500" />
  if (c.includes("snow"))  return <Wind className="h-4 w-4 text-sky-300" />
  if (c.includes("heat"))  return <Thermometer className="h-4 w-4 text-red-500" />
  return <Sun className="h-4 w-4 text-yellow-400" />
}

const authHeaders = (token: string) => ({
  "Content-Type": "application/json",
  "Authorization": "Bearer " + token,
})

const LOADING_STEPS = [
  "Extracting your travel preferences...",
  "Fetching live weather forecast...",
  "Converting budget to live INR rate...",
  "Searching for top attractions...",
  "Finding best restaurants...",
  "Finding hotels across budget tiers...",
  "Detecting local events and festivals...",
  "Building weather-aware itinerary...",
  "Almost done — finalising your plan!",
]

const HERO_SLIDES = [
  {
    image: "https://images.unsplash.com/photo-1602643163983-ed0babc39797?auto=format&fit=crop&w=2200&q=90",
    label: "Rajasthan, India",
  },
  {
    image: "https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?auto=format&fit=crop&w=2200&q=90",
    label: "Kyoto, Japan",
  },
  {
    image: "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?auto=format&fit=crop&w=2200&q=90",
    label: "Paris, France",
  },
  {
    image: "https://images.unsplash.com/photo-1533105079780-92b9be482077?auto=format&fit=crop&w=2200&q=90",
    label: "Santorini, Greece",
  },
  {
    image: "https://images.unsplash.com/photo-1516026672322-bc52d61a55d5?auto=format&fit=crop&w=2200&q=90",
    label: "Cape Town, South Africa",
  },
]

// ═══════════════════════════════════════════════════════════════════════════════
//  AUTH MODAL
// ═══════════════════════════════════════════════════════════════════════════════
function AuthModal({ onAuth }: { onAuth: (u: AuthUser) => void }) {
  const [mode,     setMode]     = useState<"login" | "signup">("login")
  const [name,     setName]     = useState("")
  const [email,    setEmail]    = useState("")
  const [password, setPassword] = useState("")
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState("")

  const submit = async () => {
    setLoading(true); setError("")
    try {
      const body: Record<string, string> = { email, password }
      if (mode === "signup") body.name = name
      const res  = await fetch(API + "/api/auth/" + mode, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      if (!res.ok || data.error) { setError(data.error || "Failed"); return }
      onAuth(data as AuthUser)
    } catch { setError("Connection error — is the backend running?") }
    finally { setLoading(false) }
  }

  return (
    <div className="auth-overlay fixed inset-0 flex items-center justify-center z-50 p-4">
      <Card className="auth-card w-full max-w-md shadow-2xl">
        <CardHeader className="text-center pb-2">
          <div className="flex justify-center mb-3">
            <div className="auth-mark h-14 w-14 rounded-full flex items-center justify-center">
              <Plane className="h-7 w-7 text-white" />
            </div>
          </div>
          <CardTitle className="text-2xl">AI Trip Planner</CardTitle>
          <CardDescription>
            {mode === "login" ? "Welcome back! Sign in to your account" : "Create your account to start planning"}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 pt-2">
          {/* Mode toggle */}
          <div className="auth-mode-switch flex rounded-lg border overflow-hidden">
            <button onClick={() => { setMode("login"); setError("") }}
              className={"flex-1 py-2 text-sm font-medium transition-colors " +
                (mode === "login" ? "bg-violet-600 text-white" : "bg-white text-gray-600 hover:bg-gray-50")}>
              <LogIn className="h-4 w-4 inline mr-1" /> Sign In
            </button>
            <button onClick={() => { setMode("signup"); setError("") }}
              className={"flex-1 py-2 text-sm font-medium transition-colors " +
                (mode === "signup" ? "bg-violet-600 text-white" : "bg-white text-gray-600 hover:bg-gray-50")}>
              <UserPlus className="h-4 w-4 inline mr-1" /> Sign Up
            </button>
          </div>

          {mode === "signup" && (
            <div className="relative">
              <User className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
              <input placeholder="Your full name" value={name} onChange={e => setName(e.target.value)}
                className="w-full border rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-400" />
            </div>
          )}
          <div className="relative">
            <Mail className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
            <input type="email" placeholder="your@email.com" value={email} onChange={e => setEmail(e.target.value)}
              className="w-full border rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-400" />
          </div>
          <div className="relative">
            <Lock className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
            <input type="password" placeholder={mode === "signup" ? "Password (min 6 chars)" : "Password"}
              value={password} onChange={e => setPassword(e.target.value)}
              onKeyDown={e => e.key === "Enter" && submit()}
              className="w-full border rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-400" />
          </div>

          {error && (
            <p className="text-sm text-red-600 flex items-center gap-1 bg-red-50 p-2 rounded-lg">
              <AlertTriangle className="h-4 w-4 shrink-0" /> {error}
            </p>
          )}

          <Button onClick={submit} disabled={loading || !email || !password || (mode === "signup" && !name)}
            className="auth-submit w-full bg-blue-600 hover:bg-violet-700">
            {loading ? <><Loader2 className="h-4 w-4 animate-spin mr-2" />Please wait...</>
              : mode === "login" ? "Sign In" : "Create Account"}
          </Button>

          <p className="text-center text-xs text-gray-500">
            Your trips are saved securely and you can access them anytime after login.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
//  PAST TRIP SUMMARY CARD
// ═══════════════════════════════════════════════════════════════════════════════
function PastTripCard({ trip, onDelete }: { trip: SavedTrip; onDelete: (id: number) => void }) {
  const [expanded, setExpanded] = useState(false)
  const ov = trip.overview_data
  const plan = trip.full_plan
  const bb = ov?.budget_breakdown

  return (
    <Card className="border-gray-200 opacity-90">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Badge variant="secondary" className="text-xs bg-gray-100 text-gray-600">
                ✅ Completed
              </Badge>
              {trip.start_date && trip.end_date && (
                <span className="text-xs text-muted-foreground">
                  {trip.start_date} → {trip.end_date}
                </span>
              )}
            </div>
            <CardTitle className="text-xl">{trip.destination}</CardTitle>
            <CardDescription>{ov?.total_days} days · saved {trip.created_at?.slice(0, 10)}</CardDescription>
          </div>
          <div className="flex items-center gap-2">
            {plan && <button onClick={() => setExpanded(v => !v)} className="text-sm text-violet-600 hover:text-violet-800">{expanded ? "Hide itinerary" : "View itinerary"}</button>}
            <button onClick={() => onDelete(trip.id)}
              className="text-gray-400 hover:text-red-500 transition-colors p-1" title="Delete trip">
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Highlights */}
        {ov?.highlights && ov.highlights.length > 0 && (
          <div>
            <p className="text-sm font-semibold mb-2 flex items-center gap-1">
              <MapPin className="h-4 w-4 text-blue-500" /> Places You Visited
            </p>
            <div className="flex flex-wrap gap-2">
              {ov.highlights.map((p, i) => (
                <Badge key={i} variant="outline" className="text-xs">{p}</Badge>
              ))}
              {ov.places_visited.length > 4 && (
                <Badge variant="secondary" className="text-xs">
                  +{ov.places_visited.length - 4} more
                </Badge>
              )}
            </div>
          </div>
        )}

        {/* Hotel */}
        {ov?.hotel_stayed && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Hotel className="h-4 w-4 text-purple-500" />
            <span>Stayed at <span className="font-medium text-foreground">{ov.hotel_stayed}</span></span>
          </div>
        )}

        {/* Budget summary */}
        {bb && (
          <div className="bg-gray-50 rounded-lg p-3 grid grid-cols-2 gap-2 text-sm">
            <div>
              <p className="text-muted-foreground text-xs">Budget</p>
              <p className="font-semibold">{fmt(ov?.budget_inr)}</p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs">Spent</p>
              <p className="font-semibold">{fmt(bb.total_estimated)}</p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs">Accommodation</p>
              <p className="font-medium">{fmt(bb.accommodation)}</p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs">Food</p>
              <p className="font-medium">{fmt(bb.food)}</p>
            </div>
          </div>
        )}

        {expanded && plan && (
          <div className="border-t pt-4 space-y-4">
            <h4 className="font-semibold">Saved itinerary</h4>
            {plan.itinerary?.map((day: DayPlan, index: number) => (
              <div key={index} className="rounded-lg border p-3">
                <p className="font-semibold">Day {day.day}: {day.title}</p>
                <ul className="mt-2 space-y-1 text-sm">
                  {day.activities?.map((activity: Activity, i: number) => (
                    <li key={i}>• {activity.time} — {activity.activity}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
//  UPCOMING TRIP FULL VIEW
// ═══════════════════════════════════════════════════════════════════════════════
function UpcomingTripCard({ trip, onDelete }: { trip: SavedTrip; onDelete: (id: number) => void }) {
  const [expanded, setExpanded] = useState(false)
  const plan = trip.full_plan
  if (!plan) return null

  const td = plan.travel_details
  const bb = plan.budget_breakdown

  return (
    <Card className="border-violet-200">
      {/* Header row */}
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Badge className="bg-violet-600 text-white text-xs">🗓 Upcoming</Badge>
              {trip.start_date && trip.end_date && (
                <span className="text-xs text-muted-foreground">{trip.start_date} → {trip.end_date}</span>
              )}
            </div>
            <CardTitle className="text-xl">{trip.destination}</CardTitle>
            <CardDescription>
              {td?.duration} days · {td?.travelers} travelers · {fmt(td?.budget_inr)}
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setExpanded(e => !e)}
              className="flex items-center gap-1 text-sm text-violet-600 hover:text-violet-800 font-medium">
              {expanded ? <><ChevronUp className="h-4 w-4" />Hide</> : <><Eye className="h-4 w-4" />View Full Plan</>}
            </button>
            <button onClick={() => onDelete(trip.id)}
              className="text-gray-400 hover:text-red-500 transition-colors p-1">
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        </div>
        {td?.overview && <p className="text-sm text-muted-foreground mt-1">{td.overview}</p>}
      </CardHeader>

      {expanded && (
        <CardContent className="pt-0 space-y-6 border-t">
          {/* Weather */}
          {plan.weather?.data_available && (
            <div className="flex items-center gap-3 p-3 rounded-lg bg-sky-50 border border-sky-200 text-sm mt-4">
              {weatherIcon(plan.weather.condition)}
              <div>
                <span className="font-medium">{plan.weather.condition} · {plan.weather.current_temp_c}°C</span>
                <span className="text-muted-foreground ml-2">{plan.weather.advice}</span>
              </div>
            </div>
          )}

          {/* Budget */}
          {bb && (
            <div className="bg-gray-50 rounded-lg p-4">
              <p className="font-semibold text-sm mb-3 flex items-center gap-1">
                <IndianRupee className="h-4 w-4" /> Budget Breakdown
              </p>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
                {[
                  { label: "Accommodation", val: bb.accommodation },
                  { label: "Food",          val: bb.food          },
                  { label: "Activities",    val: bb.activities    },
                  { label: "Transport",     val: bb.transportation},
                  { label: "Misc",          val: bb.miscellaneous },
                  { label: "Total",         val: bb.total_estimated, bold: true },
                ].map(i => (
                  <div key={i.label}>
                    <p className="text-muted-foreground text-xs">{i.label}</p>
                    <p className={"font-medium" + (i.bold ? " text-base font-bold" : "")}>{fmt(i.val)}</p>
                  </div>
                ))}
              </div>
              <p className={"mt-2 text-sm font-semibold " + (bb.within_budget ? "text-green-600" : "text-red-600")}>
                {bb.within_budget ? "✓ Within budget · " + fmt(bb.remaining) + " remaining"
                  : "⚠ Over budget by " + fmt(Math.abs(bb.remaining))}
              </p>
            </div>
          )}

          {/* Full plan tabs */}
          <Tabs defaultValue="itinerary" className="itinerary-tabs">
            <TabsList className="grid w-full grid-cols-4">
              <TabsTrigger value="itinerary"><Calendar className="h-3 w-3 mr-1" />Itinerary</TabsTrigger>
              <TabsTrigger value="places"><MapPin className="h-3 w-3 mr-1" />Places</TabsTrigger>
              <TabsTrigger value="restaurants"><UtensilsCrossed className="h-3 w-3 mr-1" />Food</TabsTrigger>
              <TabsTrigger value="hotels"><Hotel className="h-3 w-3 mr-1" />Hotels</TabsTrigger>
            </TabsList>

            <TabsContent value="itinerary" className="space-y-4 mt-3">
              {plan.itinerary.map((day, i) => (
                <DayCard
                  key={i}
                  day={day}
                  places={plan.places || []}
                  reoptLoading={false}
                  reoptDay={null}
                />
              ))}
            </TabsContent>

            <TabsContent value="places" className="mt-3">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {plan.places.map((p, i) => (
                  <div key={i} className="border rounded-lg p-3 flex gap-3">
                    <img src={p.image_url} alt={p.name}
                      className="h-16 w-16 object-cover rounded-lg shrink-0"
                      onError={e => { e.currentTarget.src = "https://picsum.photos/seed/landmark/200/200" }} />
                    <div className="min-w-0">
                      <p className="font-semibold text-sm truncate">{p.name}</p>
                      <p className="text-xs text-muted-foreground">{p.category} · {p.location}</p>
                      <div className="flex items-center gap-2 mt-1">
                        <Badge variant={p.is_outdoor ? "default" : "secondary"} className="text-xs">
                          {p.is_outdoor ? "Outdoor" : "Indoor"}
                        </Badge>
                        <span className="text-xs">{p.entry_fee_inr > 0 ? fmt(p.entry_fee_inr) : "Free"}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </TabsContent>

            <TabsContent value="restaurants" className="mt-3">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {plan.restaurants.map((r, i) => (
                  <div key={i} className="border rounded-lg p-3 flex gap-3">
                    <img src={r.image_url} alt={r.name}
                      className="h-16 w-16 object-cover rounded-lg shrink-0"
                      onError={e => { e.currentTarget.src = "https://picsum.photos/seed/restaurant/200/200" }} />
                    <div className="min-w-0">
                      <p className="font-semibold text-sm truncate">{r.name}</p>
                      <p className="text-xs text-muted-foreground">{r.cuisine} · {r.atmosphere}</p>
                      <p className="text-xs mt-1 font-medium">{fmt(r.avg_cost_per_person_inr)}/person</p>
                    </div>
                  </div>
                ))}
              </div>
            </TabsContent>

            <TabsContent value="hotels" className="mt-3">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {plan.hotels.map((h, i) => (
                  <div key={i} className="border rounded-lg p-3 flex gap-3">
                    <img src={h.image_url} alt={h.name}
                      className="h-16 w-16 object-cover rounded-lg shrink-0"
                      onError={e => { e.currentTarget.src = "https://picsum.photos/seed/hotel/200/200" }} />
                    <div className="min-w-0">
                      <p className="font-semibold text-sm truncate">{h.name}</p>
                      <p className="text-xs text-muted-foreground">{h.category} · {h.room_type}</p>
                      <p className="text-xs mt-1">
                        <span className="font-medium">{fmt(h.price_per_night_inr)}</span>/night ·
                        Total <span className="font-medium">{fmt(h.total_estimated_inr)}</span>
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </TabsContent>
          </Tabs>
        </CardContent>
      )}
    </Card>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
//  MY TRIPS PAGE
// ═══════════════════════════════════════════════════════════════════════════════
function MyTripsPage({ user, onBack }: { user: AuthUser; onBack: () => void }) {
  const [trips,   setTrips]   = useState<SavedTrip[]>([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState("")

  const loadTrips = useCallback(async () => {
    setLoading(true); setError("")
    try {
      const res  = await fetch(API + "/api/my_trips", { headers: authHeaders(user.token) })
      const data = await res.json()
      if (!res.ok) { setError(data.error || "Failed to load trips"); return }
      setTrips(data.trips || [])
    } catch { setError("Connection error") }
    finally { setLoading(false) }
  }, [user.token])

  useEffect(() => { loadTrips() }, [loadTrips])

  const deleteTrip = async (tripId: number) => {
    if (!confirm("Delete this trip?")) return
    try {
      await fetch(API + "/api/trip/" + tripId, {
        method: "DELETE", headers: authHeaders(user.token)
      })
      setTrips(t => t.filter(x => x.id !== tripId))
    } catch { alert("Delete failed") }
  }

  const upcoming = trips.filter(t => t.status === "upcoming")
  const past     = trips.filter(t => t.status === "past")

  return (
    <div className="my-trips-page space-y-8">
      <section className="my-trips-hero relative overflow-hidden rounded-[30px] px-6 py-8 text-white sm:px-9 sm:py-10">
        <div className="my-trips-hero-orb" aria-hidden="true" />
        <div className="relative z-10 flex flex-col justify-between gap-7 md:flex-row md:items-end">
          <div className="max-w-2xl">
            <p className="mb-3 text-[11px] font-bold uppercase tracking-[0.24em] text-violet-200">Your personal travel journal</p>
            <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">Every journey, <span className="font-serif italic text-amber-200">beautifully</span> kept.</h2>
            <p className="mt-3 max-w-xl text-sm leading-6 text-violet-100/90">Revisit the places you have planned, pick up where your next adventure begins, and keep all your travel details in one place.</p>
          </div>
          <Button onClick={onBack} className="h-11 rounded-full bg-white px-6 font-semibold text-violet-800 shadow-lg shadow-black/10 hover:bg-violet-50">
            <Plane className="mr-2 h-4 w-4" /> Plan a new journey
          </Button>
        </div>
        <div className="relative z-10 mt-8 grid max-w-lg grid-cols-3 gap-3 border-t border-white/15 pt-5">
          <div><p className="text-2xl font-semibold">{trips.length}</p><p className="mt-1 text-[11px] uppercase tracking-wider text-violet-200">All journeys</p></div>
          <div><p className="text-2xl font-semibold">{upcoming.length}</p><p className="mt-1 text-[11px] uppercase tracking-wider text-violet-200">Upcoming</p></div>
          <div><p className="text-2xl font-semibold">{past.length}</p><p className="mt-1 text-[11px] uppercase tracking-wider text-violet-200">Completed</p></div>
        </div>
      </section>
      <div className="my-trips-section-intro flex items-center justify-between gap-3">
        <div><p className="text-xs font-bold uppercase tracking-[0.18em] text-violet-600">Your collection</p><h3 className="mt-1 text-xl font-semibold tracking-tight">Trips worth remembering</h3></div>
        <span className="rounded-full border border-violet-100 bg-white px-3 py-1.5 text-xs font-medium text-violet-700">Private to your account</span>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
          <span className="ml-3 text-muted-foreground">Loading your trips...</span>
        </div>
      )}

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-600 text-sm flex items-center gap-2">
          <AlertTriangle className="h-4 w-4" /> {error}
        </div>
      )}

      {!loading && !error && trips.length === 0 && (
        <Card className="border-dashed">
          <CardContent className="py-16 text-center">
            <Plane className="h-12 w-12 mx-auto text-gray-300 mb-4" />
            <p className="text-lg font-medium text-gray-500">No trips saved yet</p>
            <p className="text-sm text-muted-foreground mt-1">Your generated itineraries are saved automatically and remain here until you delete them.</p>
            <Button className="mt-4" onClick={onBack}>Plan Your First Trip</Button>
          </CardContent>
        </Card>
      )}

      {!loading && upcoming.length > 0 && (
        <div className="space-y-4">
          <h3 className="font-semibold text-lg flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-violet-500 inline-block"></span>
            Upcoming Trips ({upcoming.length})
          </h3>
          {upcoming.map(t => <UpcomingTripCard key={t.id} trip={t} onDelete={deleteTrip} />)}
        </div>
      )}

      {!loading && past.length > 0 && (
        <div className="space-y-4">
          <h3 className="font-semibold text-lg flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-gray-400 inline-block"></span>
            Past Trips ({past.length})
          </h3>
          {past.map(t => <PastTripCard key={t.id} trip={t} onDelete={deleteTrip} />)}
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
//  WEATHER PANEL (used inside main planner)
// ═══════════════════════════════════════════════════════════════════════════════
function WeatherPanel({ weather }: { weather: Weather }) {
  if (!weather?.data_available) return (
    <Card className="border-dashed border-gray-300">
      <CardContent className="pt-4 pb-3">
        <p className="text-sm text-muted-foreground flex items-center gap-2">
          <Cloud className="h-4 w-4" />
          Weather data unavailable — add OPENWEATHER_API_KEY to .env for live weather
        </p>
      </CardContent>
    </Card>
  )
  return (
    <Card className="border-violet-200 bg-gradient-to-r from-blue-50 to-sky-50">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-blue-800 flex-wrap">
          {weatherIcon(weather.condition)}
          {weather.forecast_type === "seasonal" ? "Seasonal Forecast" : "Live Weather"} — {weather.city}
          {weather.forecast_type === "seasonal" && (
            <span className="text-xs font-normal bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full border border-amber-200">
              Estimate · Live forecast available ~5 days before trip
            </span>
          )}
          {weather.trip_start_date && (
            <span className="text-xs font-normal bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">
              Trip starts {weather.trip_start_date}
              {typeof weather.days_until_trip === "number" && weather.days_until_trip > 0
                ? " (" + weather.days_until_trip + " days away)" : ""}
            </span>
          )}
        </CardTitle>
        <CardDescription className="text-blue-700 font-medium">
          {weather.advice}
          {weather.seasonal_note && (
            <span className="block text-xs text-amber-600 mt-1">{weather.seasonal_note}</span>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-4 mb-4">
          <div className="text-center">
            <p className="text-3xl font-bold text-blue-800">{weather.current_temp_c}°C</p>
            <p className="text-xs text-muted-foreground">{weather.description}</p>
          </div>
          <div className="text-center">
            <p className="text-lg font-semibold">{weather.feels_like_c}°C</p>
            <p className="text-xs text-muted-foreground">Feels like</p>
          </div>
          <div className="text-center">
            <p className="text-lg font-semibold">{weather.humidity_pct}%</p>
            <p className="text-xs text-muted-foreground">Humidity</p>
          </div>
          <div className="flex items-center gap-1">
            {weather.is_outdoor_ok
              ? <CheckCircle2 className="h-5 w-5 text-green-500" />
              : <AlertTriangle className="h-5 w-5 text-amber-500" />}
            <span className="text-sm font-medium">
              {weather.is_outdoor_ok ? "Good for outdoors" : "Prefer indoors today"}
            </span>
          </div>
        </div>
        {weather.daily_forecast.length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
            {weather.daily_forecast.map((day, i) => (
              <div key={i} className={"rounded-lg p-2 text-center border " +
                (day.is_outdoor_ok ? "bg-green-50 border-green-200" : "bg-amber-50 border-amber-200")}>
                <p className="text-xs font-medium">{day.date.slice(5)}</p>
                <div className="flex justify-center my-1">{weatherIcon(day.condition)}</div>
                <p className="text-sm font-bold">{day.temp_c}°C</p>
                <p className="text-xs text-muted-foreground">{day.condition}</p>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
//  BUDGET PANEL
// ═══════════════════════════════════════════════════════════════════════════════
function BudgetPanel({ bb }: { bb: BudgetBreakdown }) {
  const cats = [
    { label: "Accommodation", value: bb.accommodation,  color: "bg-blue-500"   },
    { label: "Food & Dining", value: bb.food,            color: "bg-orange-400" },
    { label: "Activities",    value: bb.activities,      color: "bg-purple-500" },
    { label: "Transport",     value: bb.transportation,  color: "bg-teal-500"   },
    { label: "Miscellaneous", value: bb.miscellaneous,   color: "bg-gray-400"   },
  ]
  const total = bb.total_estimated || 1
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IndianRupee className="h-5 w-5" /> Budget Breakdown
        </CardTitle>
        <CardDescription>
          {bb.within_budget
            ? <span className="text-green-700 font-semibold">✓ Within budget — {fmt(bb.remaining)} remaining</span>
            : <span className="text-red-600 font-semibold">⚠ Over budget by {fmt(Math.abs(bb.remaining))}</span>}
          <span className="ml-2 text-xs">Live rate: 1 USD = ₹{bb.inr_rate?.toFixed(1)}</span>
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {cats.map(c => (
          <div key={c.label}>
            <div className="flex justify-between text-sm mb-1">
              <span>{c.label}</span>
              <span className="font-semibold">{fmt(c.value)}</span>
            </div>
            <div className="w-full bg-gray-100 rounded-full h-2">
              <div className={c.color + " h-2 rounded-full"} style={{ width: Math.min(100, (c.value / total) * 100) + "%" }} />
            </div>
          </div>
        ))}
        <div className="border-t pt-3 space-y-1">
          <div className="flex justify-between font-bold">
            <span>Total Estimated</span><span>{fmt(bb.total_estimated)}</span>
          </div>
          <div className="flex justify-between">
            <span>Your Budget</span>
            <span className="font-semibold">{fmt(bb.user_budget_inr)} (${bb.user_budget_usd})</span>
          </div>
          <div className={"flex justify-between font-bold " + (bb.within_budget ? "text-green-600" : "text-red-600")}>
            <span>{bb.within_budget ? "Remaining" : "Over Budget"}</span>
            <span>{bb.within_budget ? "+" : "-"}{fmt(Math.abs(bb.remaining))}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

const isUnverifiedLocationWarning = (message?: string) =>
  Boolean(message && /(?:unverified|not\s+verified).{0,60}(?:location|coordinates?)|(?:location|coordinates?).{0,60}(?:unverified|not\s+verified)/i.test(message))

// ═══════════════════════════════════════════════════════════════════════════════
//  DAY CARD (with re-optimize)
// ═══════════════════════════════════════════════════════════════════════════════
function DayCard({ day, places, reoptLoading, reoptDay, onReopt }: {
  day: DayPlan; places: Place[]; reoptLoading: boolean; reoptDay: number | null
  onReopt?: (dayNum: number, removed: string) => void
}) {
  const isReopt = reoptLoading && reoptDay === day.day
  const hasActivityLocationWarning = day.activities.some(
    act => isUnverifiedLocationWarning(act.travel_note)
  )
  const visibleRouteWarnings = (day.route_warnings || []).filter(
    warning => !(hasActivityLocationWarning && isUnverifiedLocationWarning(warning))
  )
  const findPlace = (act: Activity) => places.find(place =>
    (act.place_id && (place as any).id === act.place_id) ||
    place.name.trim().toLowerCase() === act.activity.trim().toLowerCase()
  )
  const heroPlace = day.activities.map(findPlace).find(place => place?.image_url)
  const meals = [
    { label: "Breakfast", val: day.meals.breakfast, time: "08:00", icon: Coffee },
    { label: "Lunch", val: day.meals.lunch, time: "13:00", icon: UtensilsCrossed },
    { label: "Dinner", val: day.meals.dinner, time: "19:00", icon: UtensilsCrossed },
  ]
  return (
    <Card className={`itinerary-day-card overflow-hidden ${day.has_event ? "itinerary-day-event" : ""}`}>
      <div className="itinerary-day-heading">
        {heroPlace?.image_url ? (
          <img src={heroPlace.image_url} alt={heroPlace.name} className="itinerary-day-cover"
            onError={e => { e.currentTarget.style.display = "none" }} />
        ) : <div className="itinerary-day-cover itinerary-day-cover-fallback"><Compass className="h-10 w-10" /></div>}
        <div className="itinerary-day-cover-shade" />
        <div className="itinerary-day-heading-content">
          <div className="flex flex-wrap items-center gap-2">
            <span className="itinerary-day-kicker">DAY {day.day}</span>
            {day.has_event && day.event_name && <Badge className="bg-white/15 text-white border border-white/25"><PartyPopper className="h-3 w-3 mr-1" />{day.event_name}</Badge>}
          </div>
          <h3 className="mt-2 font-serif text-2xl font-semibold tracking-tight text-white sm:text-3xl">{day.title}</h3>
          {day.date_label && <p className="mt-1 flex items-center gap-1.5 text-sm text-white/80"><Calendar className="h-4 w-4" />{day.date_label}</p>}
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <span className="itinerary-day-cost">Estimated day cost · {typeof day.estimated_cost_inr === "number" ? fmt(day.estimated_cost_inr) : day.estimated_cost_inr}</span>
            {onReopt && (
<Button variant="secondary" size="sm" disabled={isReopt}
              onClick={() => onReopt?.(day.day, day.activities.length > 0 ? day.activities[day.activities.length - 1].activity : "")}
              className="rounded-full bg-white/95 text-violet-800 hover:bg-white">
              {isReopt ? <><Loader2 className="h-3 w-3 animate-spin mr-1" />Re-optimizing...</> : <><RotateCcw className="h-3 w-3 mr-1" />Re-optimize day</>}
            </Button>
)}
          </div>
        </div>
      </div>

      <CardContent className="itinerary-day-content space-y-6">
        {day.weather_note && (
          <div className="itinerary-weather-note"><Cloud className="h-4 w-4 shrink-0" /><span>{day.weather_note}</span></div>
        )}

        <section>
          <div className="itinerary-section-heading">
            <div><p className="itinerary-section-eyebrow">YOUR DAY, AT A GLANCE</p><h4>Places to discover</h4></div>
            <span className="itinerary-count-pill">{day.activities.length} {day.activities.length === 1 ? "stop" : "stops"}</span>
          </div>
          <div className="itinerary-activity-list">
            {day.activities.map((act, idx) => {
              const place = findPlace(act)
              return (
                <article key={idx} className="itinerary-activity-item">
                  <div className="itinerary-activity-rail"><span className="itinerary-time-pill">{act.time}</span><span className="itinerary-rail-line" /></div>
                  <div className="itinerary-activity-card">
                    {place?.image_url ? <img src={place.image_url} alt={act.activity} className="itinerary-activity-image" onError={e => { e.currentTarget.style.display = "none" }} /> : <div className="itinerary-activity-image itinerary-activity-image-fallback"><Camera className="h-6 w-6" /></div>}
                    <div className="min-w-0 flex-1 p-4">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="min-w-0"><h5 className="font-semibold text-[#24183f]">{act.activity}</h5><p className="mt-1 text-sm leading-5 text-slate-600">{act.description}</p></div>
                        <span className="itinerary-activity-cost">{typeof act.cost_inr === "number" && act.cost_inr > 0 ? fmt(act.cost_inr) : typeof act.cost_inr === "string" ? act.cost_inr : "Free"}</span>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-xs text-slate-500">
                        <span className="inline-flex items-center gap-1"><MapPin className="h-3.5 w-3.5 text-violet-500" />{act.location}</span>
                        <span className="inline-flex items-center gap-1"><Clock className="h-3.5 w-3.5 text-violet-500" />{act.duration}</span>
                        {place?.maps_link && <a href={place.maps_link} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-semibold text-violet-700 hover:text-violet-900">View on Maps <ArrowUpRight className="h-3 w-3" /></a>}
                      </div>
                      {act.travel_note && <div className="mt-3 flex items-start gap-2 rounded-xl bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800"><AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />{act.travel_note}</div>}
                      {act.caution && !(isUnverifiedLocationWarning(act.travel_note) && isUnverifiedLocationWarning(act.caution)) && <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">⚠️ {act.caution}</div>}
                    </div>
                  </div>
                </article>
              )
            })}
          </div>
        </section>

        {visibleRouteWarnings.length > 0 && <div className="space-y-2">{visibleRouteWarnings.map((warning: string, idx: number) => <div key={idx} className="itinerary-route-warning"><AlertTriangle className="h-4 w-4 shrink-0" />{warning}</div>)}</div>}

        <section className="itinerary-meals-section">
          <div className="itinerary-section-heading"><div><p className="itinerary-section-eyebrow">PAUSE & REFUEL</p><h4>Meals along the way</h4></div><UtensilsCrossed className="h-5 w-5 text-violet-500" /></div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            {meals.map(m => { const MealIcon = m.icon; return <div key={m.label} className="itinerary-meal-card"><div className="flex items-center justify-between"><span className="flex items-center gap-2 text-sm font-semibold text-[#30234d]"><MealIcon className="h-4 w-4 text-violet-600" />{m.label}</span><span className="text-xs font-medium text-violet-600">{m.time}</span></div><p className="mt-2 text-sm leading-5 text-slate-600">{mealStr(m.val)}</p></div> })}
          </div>
        </section>

        {(day.additional_places || []).length > 0 && (
          <section className="itinerary-discovery-section">
            <div className="itinerary-section-heading"><div><p className="itinerary-section-eyebrow">IF YOU HAVE EXTRA TIME</p><h4>More to explore</h4></div><span className="itinerary-count-pill">{day.additional_places?.length} places</span></div>
            <p className="mb-4 text-sm text-slate-500">These attractions were found but could not be fitted into the timed route. They remain available as suggestions.</p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {(day.additional_places || []).map((place: AdditionalPlace, idx: number) => <div key={idx} className="itinerary-extra-place">
                {place.image_url ? <img src={place.image_url} alt={place.name} onError={e => { e.currentTarget.style.display = "none" }} /> : <div className="itinerary-extra-placeholder"><Camera className="h-5 w-5" /></div>}
                <div className="min-w-0 flex-1"><p className="font-semibold text-[#2b2045]">{place.name}</p>{place.location && <p className="mt-1 text-xs text-slate-500">{place.location}</p>}{place.reason && <p className="mt-2 text-xs leading-5 text-amber-700">{place.reason}</p>}{place.maps_link && <a className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-violet-700" href={place.maps_link} target="_blank" rel="noopener noreferrer">Explore on Maps <ArrowUpRight className="h-3 w-3" /></a>}</div>
              </div>)}
            </div>
          </section>
        )}
        {day.tips && <div className="itinerary-day-tip"><Sparkles className="h-4 w-4 shrink-0" /><div><strong>Local tip</strong><p>{day.tips}</p></div></div>}
      </CardContent>
    </Card>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
//  MAIN APP
// ═══════════════════════════════════════════════════════════════════════════════
export default function Home() {
  // Auth
  const [user,       setUser]       = useState<AuthUser | null>(null)
  const [showAuth,   setShowAuth]   = useState(false)
  const [showTrips,  setShowTrips]  = useState(false)
  const [heroImageIndex, setHeroImageIndex] = useState(0)

  // Rotate destination photography gently; respect reduced-motion preferences.
  useEffect(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches
    if (reduceMotion) return
    const interval = window.setInterval(() => {
      setHeroImageIndex(index => (index + 1) % HERO_SLIDES.length)
    }, 7000)
    return () => window.clearInterval(interval)
  }, [])

  // Planner
  const [userInput,    setUserInput]    = useState("")
  const [loading,      setLoading]      = useState(false)
  const [loadStep,     setLoadStep]     = useState(0)
  const [travelPlan,   setTravelPlan]   = useState<TravelPlan | null>(null)
  const [error,        setError]        = useState("")
  const [reoptDay,     setReoptDay]     = useState<number | null>(null)
  const [reoptLoading, setReoptLoading] = useState(false)

  // Save trip for alerts
  const [startDate,   setStartDate]   = useState("")
  const [endDate,     setEndDate]     = useState("")
  const [alertEmail,  setAlertEmail]  = useState("")
  const [alertStatus, setAlertStatus] = useState<"idle"|"sending"|"sent"|"error">("idle")
  const [alertMsg,    setAlertMsg]    = useState("")
  const [weatherAlertsEnabled, setWeatherAlertsEnabled] = useState(true)
  const [eventAlertsEnabled, setEventAlertsEnabled] = useState(true)

  // Restore session on load
  useEffect(() => {
    const stored = localStorage.getItem("trip_planner_user")
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as AuthUser
        if (parsed?.token) {
          fetch(API + "/api/auth/me", { headers: authHeaders(parsed.token) })
            .then(r => { if (r.ok) { setUser(parsed); setShowAuth(false) }
              else { localStorage.removeItem("trip_planner_user"); setUser(null); setShowAuth(false) } })
            .catch(() => { setUser(parsed); setShowAuth(false) })
        }
        else { localStorage.removeItem("trip_planner_user"); setShowAuth(false) }
      } catch { localStorage.removeItem("trip_planner_user"); setShowAuth(false) }
    } else { setShowAuth(false) }
  }, [])

  const handleAuth = (u: AuthUser) => {
    setUser(u)
    localStorage.setItem("trip_planner_user", JSON.stringify(u))
    setShowAuth(false)
    setAlertEmail(u.email)
  }

  const handleLogout = async () => {
    if (user) {
      try { await fetch(API + "/api/auth/logout", { method: "POST", headers: authHeaders(user.token) }) } catch {}
    }
    setUser(null)
    localStorage.removeItem("trip_planner_user")
    setShowTrips(false)
    setAlertEmail("")
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!user) { setShowAuth(true); setError("Please sign in or create an account before generating an itinerary."); return }
    setLoading(true); setError(""); setTravelPlan(null); setLoadStep(0)
    const interval = setInterval(() => setLoadStep(s => s < LOADING_STEPS.length - 1 ? s + 1 : s), 3500)
    try {
      const res  = await fetch(API + "/api/plan_travel", {
        method: "POST",
        headers: authHeaders(user.token),
        body: JSON.stringify({ user_input: userInput }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || "Failed")
      setTravelPlan(data)
      if (user) setAlertEmail(user.email)
      // Auto-fill trip dates from extracted travel_details
      if (data.travel_details?.start_date) setStartDate(data.travel_details.start_date)
      if (data.travel_details?.end_date)   setEndDate(data.travel_details.end_date)
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred")
    } finally { clearInterval(interval); setLoading(false) }
  }

  const handleReoptimize = async (dayNumber: number, removedAttraction: string) => {
    if (!travelPlan) return
    setReoptDay(dayNumber); setReoptLoading(true)
    try {
      // Collect all attraction names already scheduled on OTHER days
      // so the re-optimised day gets fresh places that haven't appeared elsewhere
      const usedOnOtherDays = travelPlan.itinerary
        .filter((_, i) => i !== dayNumber - 1)
        .flatMap(d => d.activities
          .filter((a: Activity) => !a.is_meal)
          .map((a: Activity) => a.activity.trim())
        )

      const res  = await fetch(API + "/api/reoptimize_day", {
        method: "POST",
        headers: authHeaders(user!.token),
        body: JSON.stringify({
          day_number: dayNumber, removed_attraction: removedAttraction,
          travel_details: travelPlan.travel_details, places: travelPlan.places,
          restaurants: travelPlan.restaurants, weather: travelPlan.weather,
          used_places: usedOnOtherDays,
          trip_id: travelPlan.saved_trip_id,
          full_plan: travelPlan,
        }),
      })
      const data = await res.json()
      if (data.day) {
        setTravelPlan(prev => {
          if (!prev) return prev
          const it = [...prev.itinerary]; it[dayNumber - 1] = data.day
          return { ...prev, itinerary: it }
        })
      }
    } catch (err) { console.error(err) }
    finally { setReoptDay(null); setReoptLoading(false) }
  }

  const saveForAlerts = async () => {
    if (!travelPlan) return
    if (!user) { setShowAuth(true); setAlertStatus("error"); setAlertMsg("Please sign in first."); return }
    setAlertStatus("sending")
    try {
      const headers: Record<string, string> = authHeaders(user.token)
      const res = await fetch(API + "/api/save_trip", {
        method: "POST", headers,
        body: JSON.stringify({
          trip_id:         travelPlan.saved_trip_id,
          destination:     travelPlan.travel_details.destination,
          duration:        travelPlan.travel_details.duration,
          travel_details:  travelPlan.travel_details,
          weather:         travelPlan.weather,
          full_plan:       travelPlan,
          start_date:      startDate,
          end_date:        endDate,
          weather_alerts:  weatherAlertsEnabled,
          event_alerts:    eventAlertsEnabled,
        }),
      })
      const data = await res.json()
      if (!res.ok) { setAlertStatus("error"); setAlertMsg(data.error || "Failed"); return }
      setAlertStatus("sent"); setAlertMsg(data.message)
    } catch { setAlertStatus("error"); setAlertMsg("Connection error") }
  }

  // If showing My Trips page
  if (showTrips && user) {
    return (
      <div className="my-trips-shell min-h-screen mx-auto p-4 sm:p-6 max-w-6xl">
        <div className="my-trips-topbar flex items-center justify-between mb-7 rounded-2xl border border-violet-100/80 bg-white/85 px-5 py-4 shadow-sm backdrop-blur-xl">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-2xl bg-gradient-to-br from-violet-600 to-indigo-700 flex items-center justify-center shadow-lg shadow-violet-200">
              <Plane className="h-4 w-4 text-white" />
            </div>
            <span className="font-bold text-lg">AI Trip Planner</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted-foreground">Hi, {user.name}</span>
            <Button variant="outline" size="sm" onClick={handleLogout}>
              <LogOut className="h-4 w-4 mr-1" />Logout
            </Button>
          </div>
        </div>
        <MyTripsPage user={user} onBack={() => setShowTrips(false)} />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#fbfaff] text-[#17152f]">
      {showAuth && <AuthModal onAuth={handleAuth} />}

      {/* Navigation */}
      <header className="relative z-20 border-b border-white/50 bg-white/75 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 lg:px-8">
          <a href="#" className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-violet-600 to-indigo-700 text-white shadow-lg shadow-violet-200">
              <Plane className="h-5 w-5" />
            </div>
            <span className="text-lg font-extrabold tracking-tight sm:text-xl">AI Travel Planner</span>
          </a>
          <nav className="hidden items-center gap-8 text-sm font-semibold text-slate-700 md:flex">
            <a href="#plan" className="transition hover:text-violet-700">Plan a Trip</a>
            <a href="#features" className="transition hover:text-violet-700">Features</a>
            <a href="#destinations" className="transition hover:text-violet-700">Destinations</a>
            {user && <button onClick={() => setShowTrips(true)} className="transition hover:text-violet-700">My Trips</button>}
          </nav>
          <div className="flex items-center gap-2">
            {user ? (
              <>
                <span className="hidden text-sm text-slate-600 sm:inline">Hi, {user.name}</span>
                <Button variant="outline" size="sm" onClick={() => setShowTrips(true)} className="rounded-full border-violet-200 bg-white">My Trips</Button>
                <Button variant="ghost" size="sm" onClick={handleLogout} className="hidden sm:inline-flex">Logout</Button>
              </>
            ) : (
              <Button variant="outline" size="sm" onClick={() => setShowAuth(true)} className="rounded-full border-violet-200 bg-white px-4 text-violet-700 hover:bg-violet-50">
                Sign in
              </Button>
            )}
            <Button size="sm" onClick={() => document.getElementById("plan")?.scrollIntoView({ behavior: "smooth" })}
              className="rounded-full bg-violet-700 px-4 text-white shadow-md shadow-violet-200 hover:bg-violet-800">
              Get started <span className="ml-1">→</span>
            </Button>
          </div>
        </div>
      </header>

      {!travelPlan && (
        <>
          {/* Hero */}
          <section className="travel-hero relative isolate overflow-hidden">
            <div className="absolute inset-0 -z-20 overflow-hidden bg-slate-200" aria-label="Rotating destination photography">
              {HERO_SLIDES.map((slide, index) => (
                <div
                  key={slide.label}
                  role="img"
                  aria-label={slide.label}
                  className={`hero-slide absolute inset-0 bg-cover bg-center ${index === heroImageIndex ? "is-active" : ""}`}
                  style={{ backgroundImage: `url("${slide.image}")` }}
                />
              ))}
            </div>
            <div className="absolute inset-0 -z-10 bg-gradient-to-r from-[#fffaf2]/95 via-[#fff7ee]/82 to-[#fff7ee]/18" />
            <div className="absolute inset-0 -z-10 bg-gradient-to-t from-[#2b1b32]/20 via-transparent to-white/10" />
            <div className="absolute bottom-5 right-6 z-10 hidden items-center gap-2 rounded-full border border-white/50 bg-white/70 px-3 py-2 text-xs font-semibold text-slate-700 shadow-sm backdrop-blur sm:flex">
              <span>{HERO_SLIDES[heroImageIndex].label}</span>
              <span className="mx-1 h-3 w-px bg-slate-300" />
              <div className="flex items-center gap-1.5" aria-label="Choose hero image">
                {HERO_SLIDES.map((slide, index) => (
                  <button key={slide.label} type="button" onClick={() => setHeroImageIndex(index)}
                    aria-label={`Show ${slide.label}`} aria-pressed={index === heroImageIndex}
                    className={`h-2 rounded-full transition-all ${index === heroImageIndex ? "w-5 bg-violet-700" : "w-2 bg-slate-400/70 hover:bg-violet-500"}`} />
                ))}
              </div>
            </div>
            <div className="mx-auto max-w-7xl px-5 pb-12 pt-14 sm:pt-20 lg:px-8 lg:pb-16">
              <div className="max-w-2xl">
                <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-violet-200/80 bg-white/75 px-4 py-2 text-xs font-bold tracking-wide text-violet-800 shadow-sm backdrop-blur">
                  <span className="text-violet-600">✦</span> AI-POWERED · PERSONALIZED · WORLDWIDE
                </div>
                <h1 className="max-w-xl text-4xl font-black leading-[1.08] tracking-tight text-[#17152f] sm:text-5xl lg:text-6xl">
                  Plan smarter trips <span className="text-violet-700">around the world.</span>
                </h1>
                <p className="mt-5 max-w-xl text-base leading-7 text-slate-700 sm:text-lg">
                  Discover remarkable places worldwide, build practical day-wise itineraries, and stay prepared with weather, events and travel updates — all in one place.
                </p>
                <div className="mt-6 flex flex-wrap gap-2 text-xs font-semibold text-slate-800">
                  {[
                    ["✧", "Personalized itineraries"],
                    ["☼", "Weather & event alerts"],
                    ["⌖", "Smart route grouping"],
                    ["☆", "Attraction coverage"],
                  ].map(([icon, label]) => (
                    <span key={label} className="inline-flex items-center gap-2 rounded-full border border-white/80 bg-white/75 px-3 py-2 shadow-sm backdrop-blur">
                      <span className="text-base text-violet-700">{icon}</span>{label}
                    </span>
                  ))}
                </div>
              </div>

              {/* Planner */}
              <div id="plan" className="mt-10 scroll-mt-8 rounded-[2rem] border border-white/80 bg-white/95 p-5 shadow-[0_24px_80px_-32px_rgba(40,25,80,0.38)] backdrop-blur-xl sm:p-7">
                <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.18em] text-violet-700">Your next adventure</p>
                    <h2 className="mt-1 text-2xl font-extrabold tracking-tight sm:text-3xl">Plan your next trip</h2>
                  </div>
                  <span className="rounded-full bg-violet-50 px-3 py-1.5 text-xs font-semibold text-violet-700">✨ Your trip, thoughtfully planned</span>
                </div>
                <form onSubmit={handleSubmit} className="space-y-4">
                  <label htmlFor="trip-prompt" className="text-sm font-semibold text-slate-700">Where would you like to go?</label>
                  <Textarea
                    id="trip-prompt"
                    placeholder="e.g. Plan a 5-day trip to Kyoto for 2 people with a $2,500 budget. We love temples, food and local culture..."
                    value={userInput} onChange={e => setUserInput(e.target.value)}
                    className="min-h-[112px] resize-y rounded-2xl border-slate-200 bg-[#fdfcff] p-4 text-sm leading-6 shadow-inner focus-visible:ring-violet-500" required />
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex flex-wrap gap-2">
                      <span className="mr-1 self-center text-xs font-semibold text-slate-500">Try:</span>
                      {["Paris · 5 days · $3,000", "Tokyo · 6 days · $3,500", "Bali · 5 days · $2,000"].map(q => (
                        <button key={q} type="button"
                          className="rounded-full border border-violet-200 bg-white px-3 py-1.5 text-xs font-medium text-violet-800 transition hover:border-violet-400 hover:bg-violet-50"
                          onClick={() => setUserInput("Plan a trip to " + q.replaceAll("·", "").replaceAll("  ", " ") + " for 2 people")}>
                          {q}
                        </button>
                      ))}
                    </div>
                    <Button type="submit" disabled={loading}
                      className="h-12 rounded-xl bg-gradient-to-r from-violet-700 to-indigo-700 px-6 text-sm font-bold text-white shadow-lg shadow-violet-200 transition hover:-translate-y-0.5 hover:from-violet-800 hover:to-indigo-800">
                      {loading
                        ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />{LOADING_STEPS[loadStep]}</>
                        : <>Generate itinerary <span className="ml-2">→</span></>}
                    </Button>
                  </div>
                </form>
                {error && <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>}
                {!user && <p className="mt-3 text-xs text-slate-500">You'll be asked to sign in when you generate your itinerary. Your trip history stays with your account.</p>}
              </div>
              <div className="mt-5 flex flex-wrap items-center gap-2 text-sm">
                <span className="mr-1 font-bold text-slate-800">Popular destinations</span>
                {["Paris", "Tokyo", "Bali", "Cape Town", "Istanbul"].map(city => (
                  <button key={city} type="button" onClick={() => setUserInput(`Plan a 3-day trip to ${city} for 2 travelers. Include major attractions, local food and a balanced budget.`)}
                    className="rounded-full border border-white/80 bg-white/80 px-4 py-2 text-xs font-semibold text-slate-800 shadow-sm backdrop-blur transition hover:-translate-y-0.5 hover:border-violet-300 hover:text-violet-800">
                    {city}
                  </button>
                ))}
              </div>
            </div>
          </section>

          {/* Product value proposition */}
          <section id="features" className="mx-auto max-w-7xl scroll-mt-8 px-5 py-16 lg:px-8 lg:py-20">
            <div className="mx-auto mb-10 max-w-2xl text-center">
              <span className="rounded-full bg-violet-100 px-4 py-2 text-xs font-bold uppercase tracking-wider text-violet-700">Travel planning, reimagined</span>
              <h2 className="mt-5 text-3xl font-black tracking-tight sm:text-4xl">More than an itinerary generator</h2>
              <p className="mt-3 text-slate-600">Thoughtful planning that helps turn a destination into a trip you can actually follow.</p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {[
                { icon: "✦", title: "Personalized plans", desc: "Day-wise suggestions shaped around your interests, budget and travel duration." },
                { icon: "☼", title: "Weather & event alerts", desc: "Stay informed about relevant weather changes and events during your trip." },
                { icon: "⌖", title: "Smarter daily routes", desc: "Group nearby attractions sensibly and respect practical visiting hours." },
                { icon: "▤", title: "One trip workspace", desc: "Explore places, food and stays, then revisit saved plans in your trip history." },
              ].map(item => (
                <div key={item.title} className="rounded-3xl border border-violet-100 bg-white p-6 shadow-[0_12px_35px_-28px_rgba(50,30,90,0.35)] transition hover:-translate-y-1 hover:shadow-lg">
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-violet-50 text-2xl text-violet-700">{item.icon}</div>
                  <h3 className="mt-5 text-lg font-extrabold">{item.title}</h3>
                  <p className="mt-2 text-sm leading-6 text-slate-600">{item.desc}</p>
                </div>
              ))}
            </div>
          </section>

          {/* Destinations */}
          <section id="destinations" className="bg-white py-16 lg:py-20">
            <div className="mx-auto max-w-7xl px-5 lg:px-8">
              <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.18em] text-violet-700">Find your somewhere</p>
                  <h2 className="mt-2 text-3xl font-black tracking-tight sm:text-4xl">Where will you go next?</h2>
                </div>
                <p className="max-w-md text-sm leading-6 text-slate-600">Choose a starting point. You can personalize the trip with your own dates, interests and budget.</p>
              </div>
              <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
                {[
                  { name: "Paris", sub: "Art, cafés & iconic streets", image: "photo-1502602898657-3e91760cbb34" },
                  { name: "Kyoto", sub: "Temples & quiet gardens", image: "photo-1493976040374-85c8e12f0c0e" },
                  { name: "Bali", sub: "Island escapes & rice terraces", image: "photo-1537996194471-e657df975ab4" },
                  { name: "Cape Town", sub: "Coastlines & mountain views", image: "photo-1580060839134-75a5edca2e99" },
                  { name: "Istanbul", sub: "Historic quarters & bazaars", image: "photo-1524231757912-21f4fe3a7200" },
                ].map(place => (
                  <button key={place.name} type="button" onClick={() => { setUserInput(`Plan a 3-day trip to ${place.name} for 2 travelers with popular attractions and local experiences.`); document.getElementById("plan")?.scrollIntoView({ behavior: "smooth" }) }}
                    className="group relative h-64 overflow-hidden rounded-3xl text-left shadow-md">
                    <img src={`https://images.unsplash.com/${place.image}?auto=format&fit=crop&w=700&q=85`} alt={place.name}
                      className="absolute inset-0 h-full w-full object-cover transition duration-700 group-hover:scale-110" />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-black/10 to-transparent" />
                    <div className="absolute inset-x-0 bottom-0 p-5 text-white">
                      <h3 className="text-xl font-extrabold">{place.name}</h3>
                      <p className="mt-1 text-xs text-white/85">{place.sub}</p>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </section>

          {/* How it works */}
          <section className="mx-auto max-w-7xl px-5 py-16 lg:px-8 lg:py-20">
            <div className="mx-auto max-w-2xl text-center">
              <span className="rounded-full bg-violet-100 px-4 py-2 text-xs font-bold text-violet-700">HOW IT WORKS</span>
              <h2 className="mt-5 text-3xl font-black tracking-tight sm:text-4xl">Your trip in three simple steps</h2>
              <p className="mt-3 text-slate-600">From a travel idea to a considered itinerary in minutes.</p>
            </div>
            <div className="mt-10 grid gap-5 md:grid-cols-3">
              {[
                { n: "01", icon: "▤", title: "Tell us your plan", desc: "Share your destination, dates, budget, group size and interests." },
                { n: "02", icon: "✧", title: "Let AI organize it", desc: "Discover attractions and arrange them into practical day-wise plans." },
                { n: "03", icon: "⌖", title: "Explore with confidence", desc: "Review places, food, stays, weather and updates in one workspace." },
              ].map(step => (
                <div key={step.n} className="rounded-3xl border border-violet-100 bg-white p-7 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-black tracking-widest text-violet-300">{step.n}</span>
                    <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-violet-50 text-2xl text-violet-700">{step.icon}</span>
                  </div>
                  <h3 className="mt-6 text-xl font-extrabold">{step.title}</h3>
                  <p className="mt-2 text-sm leading-6 text-slate-600">{step.desc}</p>
                </div>
              ))}
            </div>
          </section>

          <footer className="border-t border-violet-100 bg-white">
            <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-3 px-5 py-7 text-center text-xs text-slate-500 sm:flex-row sm:text-left lg:px-8">
              <span className="font-bold text-slate-700">AI Travel Planner</span>
              <span>Plan thoughtfully. Travel meaningfully.</span>
              <button onClick={() => document.getElementById("plan")?.scrollIntoView({ behavior: "smooth" })} className="font-semibold text-violet-700 hover:text-violet-900">Start planning ↑</button>
            </div>
          </footer>
        </>
      )}

      {/* Results */}
      {travelPlan && (
        <div className="itinerary-shell mx-auto max-w-6xl space-y-7 px-4 py-7 sm:px-6">
          <div className="itinerary-page-intro flex flex-wrap items-center justify-between gap-3">
            <div><p className="text-[11px] font-bold uppercase tracking-[0.22em] text-violet-600">Your journey, thoughtfully planned</p><p className="mt-1 text-sm text-slate-500">A little inspiration. A lot less planning.</p></div>
            <span className="rounded-full border border-violet-100 bg-white px-3 py-1.5 text-xs font-medium text-violet-700 shadow-sm">Personalised travel plan</span>
          </div>
          {/* Summary header */}
          <Card className="itinerary-summary relative overflow-hidden border-0 bg-gradient-to-br from-[#211443] via-[#433078] to-[#312b67] text-white shadow-2xl shadow-violet-200/70">
            <div className="itinerary-summary-glow" aria-hidden="true" />
            <CardHeader className="relative z-10">
              <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.24em] text-violet-200">Your next destination</p>
              <CardTitle className="font-serif text-3xl font-medium tracking-tight text-white sm:text-4xl">{travelPlan.travel_details.destination}</CardTitle>
              <CardDescription className="mt-2 max-w-3xl text-sm leading-6 text-violet-100">{travelPlan.travel_details.overview}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                  { label: "Duration",  val: travelPlan.travel_details.duration + " days" },
                  { label: "Budget",    val: fmt(travelPlan.travel_details.budget_inr)     },
                  { label: "Travelers", val: String(travelPlan.travel_details.travelers)   },
                  { label: "Type",      val: travelPlan.travel_details.travel_type         },
                ].map(i => (
                  <div key={i.label} className="itinerary-stat-tile">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-violet-200">{i.label}</p>
                    <p className="mt-1 text-lg font-semibold text-white">{i.val}</p>
                  </div>
                ))}
                {travelPlan.travel_details.start_date && (
                  <div className="col-span-2">
                    <p className="text-xs text-violet-200">Trip Dates</p>
                    <p className="text-base font-bold text-white">
                      {travelPlan.travel_details.start_date} → {travelPlan.travel_details.end_date}
                      {typeof travelPlan.travel_details.days_until_trip === "number" &&
                        travelPlan.travel_details.days_until_trip > 0 &&
                        <span className="text-sm font-normal ml-2 opacity-80">
                          ({travelPlan.travel_details.days_until_trip} days away)
                        </span>
                      }
                    </p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          <WeatherPanel weather={travelPlan.weather} />
          {travelPlan.budget_breakdown && <BudgetPanel bb={travelPlan.budget_breakdown} />}

          {/* ── Save + Alert Card ─────────────────────────────────────── */}
          <Card className={
            alertStatus === "sent"  ? "border-green-300 bg-green-50" :
            alertStatus === "error" ? "border-red-300 bg-red-50"     :
            "border-indigo-200 bg-indigo-50"
          }>
            <CardHeader className="pb-3">
              <CardTitle className="text-indigo-800 text-base flex items-center gap-2">
                🔔 Save Trip & Get Alerts
              </CardTitle>
              <CardDescription className="text-indigo-700">
                Save your trip to view it later in "My Trips" and receive selected weather and event email alerts. Checks run every 6 hours while the backend service is active.
                <span className="ml-1 font-medium">Your itinerary is automatically saved to your account.</span>
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {alertStatus === "sent" ? (
                <div className="flex items-start gap-3 text-green-800">
                  <CheckCircle2 className="h-5 w-5 shrink-0 mt-0.5" />
                  <div>
                    <p className="font-semibold">Trip saved!</p>
                    <p className="text-sm mt-1">{alertMsg}</p>
                  </div>
                </div>
              ) : (
                <>
                  {/* Travel date pickers */}
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs font-medium text-indigo-800 mb-1 block">Trip Start Date</label>
                      <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)}
                        className="w-full border border-indigo-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white" />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-indigo-800 mb-1 block">Trip End Date</label>
                      <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)}
                        className="w-full border border-indigo-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white" />
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-3 items-center">
                    <span className="text-sm text-indigo-800">Alerts will be sent to <strong>{user?.email}</strong></span>
                    <Button onClick={saveForAlerts}
                      disabled={alertStatus === "sending" || !user}
                      className="bg-indigo-600 hover:bg-indigo-700 text-white">
                      {alertStatus === "sending"
                        ? <><Loader2 className="h-4 w-4 animate-spin mr-2" />Saving...</>
                        : "🔔 Save & Activate Alerts"}
                    </Button>
                  </div>
                  {alertStatus === "error" && (
                    <p className="text-sm text-red-600 flex items-center gap-1">
                      <AlertTriangle className="h-4 w-4" /> {alertMsg}
                    </p>
                  )}
                  <div className="flex flex-wrap gap-4 text-xs text-indigo-700">
                    <label className="inline-flex items-center gap-2">
                      <input type="checkbox" checked={weatherAlertsEnabled}
                        onChange={e => setWeatherAlertsEnabled(e.target.checked)} />
                      🌦️ Weather change alerts
                    </label>
                    <label className="inline-flex items-center gap-2">
                      <input type="checkbox" checked={eventAlertsEnabled}
                        onChange={e => setEventAlertsEnabled(e.target.checked)} />
                      🎉 Event update alerts
                    </label>
                    <span>📁 View in My Trips after login</span>
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          {/* Tabs */}
          <Tabs defaultValue="itinerary">
            <TabsList className="grid w-full grid-cols-4">
              <TabsTrigger value="itinerary"><Calendar className="h-4 w-4 mr-1" />Itinerary</TabsTrigger>
              <TabsTrigger value="places"><MapPin className="h-4 w-4 mr-1" />Places ({travelPlan.places.length})</TabsTrigger>
              <TabsTrigger value="restaurants"><UtensilsCrossed className="h-4 w-4 mr-1" />Food ({travelPlan.restaurants.length})</TabsTrigger>
              <TabsTrigger value="hotels"><Hotel className="h-4 w-4 mr-1" />Hotels ({travelPlan.hotels.length})</TabsTrigger>
            </TabsList>

            <TabsContent value="itinerary" className="space-y-4">
              <div className="flex items-center gap-2 p-3 bg-blue-50 rounded-lg text-sm text-blue-800 border border-violet-200">
                <RefreshCw className="h-4 w-4 shrink-0" />
                <span>Each day has a <strong>Re-optimize</strong> button — click it to swap the last attraction and regenerate that day in real time.</span>
              </div>
              {travelPlan.itinerary.map((day, i) => (
                <DayCard key={i} day={day} places={travelPlan.places} reoptLoading={reoptLoading}
                  reoptDay={reoptDay} onReopt={handleReoptimize} />
              ))}
            </TabsContent>

            <TabsContent value="places">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {travelPlan.places.map((place, idx) => (
                  <Card key={idx}>
                    <div className="relative h-48">
                      <img src={place.image_url} alt={place.name}
                        className="w-full h-full object-cover rounded-t-lg"
                        onError={e => { e.currentTarget.src = "https://picsum.photos/seed/landmark/800/600" }} />
                      <div className="absolute top-2 right-2">
                        <Badge className={place.is_outdoor ? "bg-green-600" : "bg-indigo-600"}>
                          {place.is_outdoor ? "Outdoor" : "Indoor"}
                        </Badge>
                      </div>
                    </div>
                    <CardHeader>
                      <div className="flex justify-between items-start">
                        <CardTitle className="text-lg">{place.name}</CardTitle>
                        <Badge variant="outline">{place.category}</Badge>
                      </div>
                      <StarRow rating={place.rating} />
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <p className="text-sm">{place.description}</p>
                      <div className="grid grid-cols-2 gap-2 text-sm">
                        <div><span className="text-muted-foreground">Opens: </span>{place.open_time}</div>
                        <div><span className="text-muted-foreground">Closes: </span>{place.close_time}</div>
                        <div><span className="text-muted-foreground">Best time: </span>{place.best_time}</div>
                        <div><span className="text-muted-foreground">Entry: </span>
                          {place.entry_fee_inr > 0 ? fmt(place.entry_fee_inr) : "Free"}
                        </div>
                      </div>
                      {place.tips && <div className="border p-2 rounded text-sm bg-amber-50"><span className="font-semibold">Tip: </span>{place.tips}</div>}
                      <div className="flex flex-wrap gap-1">
                        {(place.tags || []).map((t, i) => <Badge key={i} variant="secondary" className="text-xs">{t}</Badge>)}
                      </div>
                      <a href={place.maps_link} target="_blank" rel="noopener noreferrer">
                        <Button className="w-full" variant="outline" size="sm">View on Maps</Button>
                      </a>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </TabsContent>

            <TabsContent value="restaurants">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {travelPlan.restaurants.map((r, idx) => (
                  <Card key={idx}>
                    <div className="h-48">
                      <img src={r.image_url} alt={r.name}
                        className="w-full h-full object-cover rounded-t-lg"
                        onError={e => { e.currentTarget.src = "https://picsum.photos/seed/restaurant/800/600" }} />
                    </div>
                    <CardHeader>
                      <div className="flex justify-between items-start">
                        <CardTitle className="text-lg">{r.name}</CardTitle>
                        <Badge>{r.budget_level}</Badge>
                      </div>
                      <p className="text-sm text-muted-foreground">{r.cuisine}</p>
                      <StarRow rating={r.rating} />
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <p className="text-sm">{r.description}</p>
                      {r.over_budget_guideline && (
                        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
                          Above the suggested food budget. Shown as an optional recommendation.
                        </p>
                      )}
                      <div className="grid grid-cols-2 gap-2 text-sm">
                        <div><span className="text-muted-foreground">Per person: </span>{fmt(r.avg_cost_per_person_inr)}</div>
                        <div><span className="text-muted-foreground">Vibe: </span>{r.atmosphere}</div>
                        <div><span className="text-muted-foreground">Best for: </span>{r.best_time}</div>
                        {r.reservation_needed && <div className="text-amber-600 font-medium">Reservation needed</div>}
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {r.specialties.map((s, i) => <Badge key={i} variant="secondary" className="text-xs">{s}</Badge>)}
                      </div>
                      <a href={r.maps_link} target="_blank" rel="noopener noreferrer">
                        <Button className="w-full" variant="outline" size="sm">View on Maps</Button>
                      </a>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </TabsContent>

            <TabsContent value="hotels">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {travelPlan.hotels.map((h, idx) => (
                  <Card key={idx}>
                    <div className="h-48">
                      <img src={h.image_url} alt={h.name}
                        className="w-full h-full object-cover rounded-t-lg"
                        onError={e => { e.currentTarget.src = "https://picsum.photos/seed/hotel/800/600" }} />
                    </div>
                    <CardHeader>
                      <div className="flex justify-between items-start">
                        <CardTitle className="text-lg">{h.name}</CardTitle>
                        <Badge>{h.category}</Badge>
                      </div>
                      <StarRow rating={h.rating} />
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <p className="text-sm">{h.description}</p>
                      {h.over_budget_guideline && (
                        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
                          Above the suggested accommodation budget. Shown as an optional recommendation.
                        </p>
                      )}
                      <div className="grid grid-cols-2 gap-2 text-sm">
                        <div><span className="text-muted-foreground">Per night: </span>{fmt(h.price_per_night_inr)}</div>
                        <div className="font-semibold"><span className="text-muted-foreground font-normal">Total: </span>{fmt(h.total_estimated_inr)}</div>
                        <div><span className="text-muted-foreground">Room: </span>{h.room_type}</div>
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {(h.amenities || []).slice(0, 6).map((a, i) => <Badge key={i} variant="secondary" className="text-xs">{a}</Badge>)}
                      </div>
                      {h.booking_tip && <div className="border p-2 rounded text-sm bg-amber-50"><span className="font-semibold">Tip: </span>{h.booking_tip}</div>}
                      <a href={h.maps_link} target="_blank" rel="noopener noreferrer">
                        <Button className="w-full" variant="outline" size="sm">View on Maps</Button>
                      </a>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </TabsContent>
          </Tabs>

          <div className="text-center pt-8">
            <Button variant="outline" onClick={() => { setTravelPlan(null); setUserInput(""); setAlertStatus("idle") }}>
              <Plane className="mr-2 h-4 w-4" /> Plan Another Trip
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
