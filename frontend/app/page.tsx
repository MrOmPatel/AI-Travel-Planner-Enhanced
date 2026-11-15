'use client'
import { useState, useEffect, useCallback } from "react"
import {
  Loader2, Plane, MapPin, Hotel, UtensilsCrossed, Calendar,
  RefreshCw, Thermometer, CloudRain, Sun, Cloud, Wind, Zap,
  Clock, IndianRupee, AlertTriangle, CheckCircle2, PartyPopper,
  RotateCcw, LogIn, LogOut, UserPlus, History, Eye, Trash2,
  ChevronDown, ChevronUp, Lock, Mail, User
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
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <Card className="w-full max-w-md shadow-2xl">
        <CardHeader className="text-center pb-2">
          <div className="flex justify-center mb-3">
            <div className="h-14 w-14 rounded-full bg-blue-600 flex items-center justify-center">
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
          <div className="flex rounded-lg border overflow-hidden">
            <button onClick={() => { setMode("login"); setError("") }}
              className={"flex-1 py-2 text-sm font-medium transition-colors " +
                (mode === "login" ? "bg-blue-600 text-white" : "bg-white text-gray-600 hover:bg-gray-50")}>
              <LogIn className="h-4 w-4 inline mr-1" /> Sign In
            </button>
            <button onClick={() => { setMode("signup"); setError("") }}
              className={"flex-1 py-2 text-sm font-medium transition-colors " +
                (mode === "signup" ? "bg-blue-600 text-white" : "bg-white text-gray-600 hover:bg-gray-50")}>
              <UserPlus className="h-4 w-4 inline mr-1" /> Sign Up
            </button>
          </div>

          {mode === "signup" && (
            <div className="relative">
              <User className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
              <input placeholder="Your full name" value={name} onChange={e => setName(e.target.value)}
                className="w-full border rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
            </div>
          )}
          <div className="relative">
            <Mail className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
            <input type="email" placeholder="your@email.com" value={email} onChange={e => setEmail(e.target.value)}
              className="w-full border rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
          </div>
          <div className="relative">
            <Lock className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
            <input type="password" placeholder={mode === "signup" ? "Password (min 6 chars)" : "Password"}
              value={password} onChange={e => setPassword(e.target.value)}
              onKeyDown={e => e.key === "Enter" && submit()}
              className="w-full border rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400" />
          </div>

          {error && (
            <p className="text-sm text-red-600 flex items-center gap-1 bg-red-50 p-2 rounded-lg">
              <AlertTriangle className="h-4 w-4 shrink-0" /> {error}
            </p>
          )}

          <Button onClick={submit} disabled={loading || !email || !password || (mode === "signup" && !name)}
            className="w-full bg-blue-600 hover:bg-blue-700">
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
            {plan && <button onClick={() => setExpanded(v => !v)} className="text-sm text-blue-600 hover:text-blue-800">{expanded ? "Hide itinerary" : "View itinerary"}</button>}
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
    <Card className="border-blue-200">
      {/* Header row */}
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Badge className="bg-blue-600 text-white text-xs">🗓 Upcoming</Badge>
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
              className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800 font-medium">
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
          <Tabs defaultValue="itinerary">
            <TabsList className="grid w-full grid-cols-4">
              <TabsTrigger value="itinerary"><Calendar className="h-3 w-3 mr-1" />Itinerary</TabsTrigger>
              <TabsTrigger value="places"><MapPin className="h-3 w-3 mr-1" />Places</TabsTrigger>
              <TabsTrigger value="restaurants"><UtensilsCrossed className="h-3 w-3 mr-1" />Food</TabsTrigger>
              <TabsTrigger value="hotels"><Hotel className="h-3 w-3 mr-1" />Hotels</TabsTrigger>
            </TabsList>

            <TabsContent value="itinerary" className="space-y-3 mt-3">
              {plan.itinerary.map((day, i) => (
                <div key={i} className="border rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <Badge variant="outline">Day {day.day}</Badge>
                    <span className="font-semibold text-sm">{day.title}</span>
                    {day.has_event && day.event_name && (
                      <Badge className="bg-purple-600 text-white text-xs">
                        <PartyPopper className="h-3 w-3 mr-1" />{day.event_name}
                      </Badge>
                    )}
                  </div>
                  {day.weather_note && (
                    <p className="text-xs text-sky-700 bg-sky-50 p-2 rounded mb-2">{day.weather_note}</p>
                  )}
                  <div className="space-y-2">
                    {day.activities.map((a, j) => (
                      <div key={j} className="flex gap-2 text-sm">
                        <Badge variant="secondary" className="text-xs shrink-0">{a.time}</Badge>
                        <div>
                          <span className="font-medium">{a.activity}</span>
                          <span className="text-muted-foreground ml-2">{a.location}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="grid grid-cols-3 gap-2 mt-3 text-xs bg-orange-50 rounded p-2">
                    {[
                      { l: "Breakfast", v: day.meals.breakfast },
                      { l: "Lunch",     v: day.meals.lunch     },
                      { l: "Dinner",    v: day.meals.dinner    },
                    ].map(m => (
                      <div key={m.l}>
                        <p className="font-semibold">{m.l}</p>
                        <p className="text-muted-foreground">{mealStr(m.v)}</p>
                      </div>
                    ))}
                  </div>
                  {day.tips && <p className="text-xs text-amber-700 mt-2">💡 {day.tips}</p>}
                </div>
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
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <History className="h-6 w-6 text-blue-600" /> My Trips
          </h2>
          <p className="text-muted-foreground text-sm mt-1">
            Your generated itineraries remain available until you manually delete them.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={onBack}>
          <Plane className="h-4 w-4 mr-1" /> Plan New Trip
        </Button>
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
            <span className="h-2 w-2 rounded-full bg-blue-500 inline-block"></span>
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
    <Card className="border-blue-200 bg-gradient-to-r from-blue-50 to-sky-50">
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
function DayCard({ day, reoptLoading, reoptDay, onReopt }: {
  day: DayPlan; reoptLoading: boolean; reoptDay: number | null
  onReopt: (dayNum: number, removed: string) => void
}) {
  const isReopt = reoptLoading && reoptDay === day.day
  const hasActivityLocationWarning = day.activities.some(
    act => isUnverifiedLocationWarning(act.travel_note)
  )
  const visibleRouteWarnings = (day.route_warnings || []).filter(
    warning => !(hasActivityLocationWarning && isUnverifiedLocationWarning(warning))
  )
  return (
    <Card className={day.has_event ? "border-purple-300 bg-purple-50/30" : ""}>
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="flex items-center gap-2 flex-wrap">
              Day {day.day}: {day.title}
              {day.has_event && day.event_name && (
                <Badge className="bg-purple-600 text-white">
                  <PartyPopper className="h-3 w-3 mr-1" />{day.event_name}
                </Badge>
              )}
            </CardTitle>
            {day.date_label && (
              <p className="text-xs text-blue-600 font-medium mt-0.5 flex items-center gap-1">
                <Calendar className="h-3 w-3" />{day.date_label}
              </p>
            )}
            <CardDescription className="mt-1">
              Est. cost: {typeof day.estimated_cost_inr === "number" ? fmt(day.estimated_cost_inr) : day.estimated_cost_inr}
            </CardDescription>
          </div>
          <Button variant="outline" size="sm" disabled={isReopt}
              onClick={() => onReopt(day.day, day.activities.length > 0
                ? day.activities[day.activities.length - 1].activity : "")}>
              {isReopt
                ? <><Loader2 className="h-3 w-3 animate-spin mr-1" />Re-optimizing...</>
                : <><RotateCcw className="h-3 w-3 mr-1" />Re-optimize Day</>}
          </Button>
        </div>
        {day.weather_note && (
          <div className="flex items-start gap-2 mt-2 p-2 rounded-lg bg-sky-50 border border-sky-200 text-sm text-sky-800">
            <Cloud className="h-4 w-4 mt-0.5 shrink-0" /><span>{day.weather_note}</span>
          </div>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {day.activities.map((act, idx) => (
          <div key={idx} className="border-l-4 border-blue-200 pl-4">
            <div className="flex gap-3 flex-wrap">
              <Badge variant="outline" className="flex items-center gap-1">
                <Clock className="h-3 w-3" />{act.time}
              </Badge>
              <div className="flex-1">
                <h4 className="font-semibold">{act.activity}</h4>
                <p className="text-sm text-muted-foreground mt-1">{act.description}</p>
                <div className="flex flex-wrap gap-3 mt-2 text-sm text-muted-foreground">
                  <span className="flex items-center gap-1"><MapPin className="h-3 w-3" />{act.location}</span>
                  <span>{act.duration}</span>
                  <span className="font-medium text-foreground">
                    {typeof act.cost_inr === "number" && act.cost_inr > 0 ? fmt(act.cost_inr)
                      : typeof act.cost_inr === "string" ? act.cost_inr : "Free"}
                  </span>
                  {act.travel_note && (
                    <span className="flex items-center gap-1 text-amber-700">
                      <AlertTriangle className="h-3 w-3 shrink-0" />{act.travel_note}
                    </span>
                  )}
                </div>
                {act.caution && !(
                  isUnverifiedLocationWarning(act.travel_note) &&
                  isUnverifiedLocationWarning(act.caution)
                ) && (
                  <div className="mt-2 flex items-start gap-2 p-2 rounded-md bg-amber-50 border border-amber-300 text-sm text-amber-800">
                    <span className="shrink-0">⚠️</span>
                    <span>{act.caution}</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
        {visibleRouteWarnings.length > 0 && (
          <div className="space-y-2">
            {visibleRouteWarnings.map((warning: string, idx: number) => (
              <div key={idx} className="p-2 rounded-md bg-amber-50 border border-amber-200 text-sm text-amber-800">
                ⚠️ {warning}
              </div>
            ))}
          </div>
        )}
        {(day.additional_places || []).length > 0 && (
          <div className="mt-4 border rounded-lg p-3">
            <h4 className="font-semibold text-sm mb-2">Additional places to explore</h4>
            <p className="text-xs text-muted-foreground mb-3">
              These attractions were found but could not be fitted into the timed route.
              They are still available as suggestions.
            </p>
            <div className="space-y-3">
              {(day.additional_places || []).map((place: any, idx: number) => (
                <div key={idx} className="flex gap-3 text-sm">
                  {place.image_url && (
                    <img src={place.image_url} alt={place.name}
                      className="h-14 w-14 object-cover rounded-md shrink-0"
                      onError={e => { e.currentTarget.style.display = "none" }} />
                  )}
                  <div className="min-w-0">
                    <p className="font-medium">{place.name}</p>
                    {place.location && <p className="text-xs text-muted-foreground">{place.location}</p>}
                    {place.reason && <p className="text-xs text-amber-700 mt-1">{place.reason}</p>}
                    {place.maps_link && (
                      <a className="text-xs text-blue-600 underline" href={place.maps_link}
                        target="_blank" rel="noopener noreferrer">View on Maps</a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="grid grid-cols-3 gap-3 mt-4 bg-orange-50 rounded-lg p-3">
          {[
            { label: "Breakfast", val: day.meals.breakfast },
            { label: "Lunch",     val: day.meals.lunch     },
            { label: "Dinner",    val: day.meals.dinner    },
          ].map(m => (
            <div key={m.label}>
              <p className="font-semibold text-sm flex items-center gap-1">
                <UtensilsCrossed className="h-3 w-3" />{m.label}
              </p>
              <p className="text-sm text-muted-foreground">{mealStr(m.val)}</p>
            </div>
          ))}
        </div>
        {day.tips && (
          <div className="border p-3 rounded-lg bg-amber-50 text-sm">
            <span className="font-semibold">💡 Tip: </span>{day.tips}
          </div>
        )}
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
  const [showAuth,   setShowAuth]   = useState(true)
  const [showTrips,  setShowTrips]  = useState(false)

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
              else { localStorage.removeItem("trip_planner_user"); setUser(null); setShowAuth(true) } })
            .catch(() => { setUser(parsed); setShowAuth(false) })
        }
        else { localStorage.removeItem("trip_planner_user"); setShowAuth(true) }
      } catch { localStorage.removeItem("trip_planner_user"); setShowAuth(true) }
    } else { setShowAuth(true) }
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
      <div className="container mx-auto p-4 max-w-4xl">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-full bg-blue-600 flex items-center justify-center">
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
    <div className="container mx-auto p-4 max-w-6xl">
      {showAuth && <AuthModal onAuth={handleAuth} />}

      {/* Top nav */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-full bg-blue-600 flex items-center justify-center">
            <Plane className="h-4 w-4 text-white" />
          </div>
          <span className="font-bold text-lg">AI Trip Planner</span>
        </div>
        <div className="flex items-center gap-2">
          {user ? (
            <>
              <Button variant="outline" size="sm" onClick={() => setShowTrips(true)}>
                <History className="h-4 w-4 mr-1" />My Trips
              </Button>
              <span className="text-sm text-muted-foreground hidden sm:inline">Hi, {user.name}</span>
              <Button variant="ghost" size="sm" onClick={handleLogout}>
                <LogOut className="h-4 w-4 mr-1" />Logout
              </Button>
            </>
          ) : (
            <Button size="sm" onClick={() => setShowAuth(true)} className="bg-blue-600 hover:bg-blue-700">
              <LogIn className="h-4 w-4 mr-1" />Sign In / Sign Up
            </Button>
          )}
        </div>
      </div>

      {/* Header */}
      {!travelPlan && (
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold mb-2">Plan Your Perfect Trip</h1>
          <p className="text-muted-foreground">
            Weather-aware · Live INR pricing · Event detection · Email alerts · Trip history
          </p>
          <div className="flex flex-wrap justify-center gap-2 mt-3">
            {["🌤 Live Weather", "💱 Live INR Rate", "🎉 Event Detection", "🔄 Re-optimize Days", "📧 Email Alerts", "📁 Trip History"].map(f => (
              <Badge key={f} variant="secondary" className="text-xs">{f}</Badge>
            ))}
          </div>
        </div>
      )}

      {/* Input form */}
      {!travelPlan && (
        <Card className="max-w-3xl mx-auto">
          <CardHeader>
            <CardTitle>Describe Your Dream Trip</CardTitle>
            <CardDescription>Tell us your destination, duration, budget (USD or ₹), and interests</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <Textarea
                placeholder="e.g. Plan a 5-day trip to Jaipur for 2 people with Rs 50,000 budget. We love history, forts, and street food..."
                value={userInput} onChange={e => setUserInput(e.target.value)}
                className="min-h-[130px]" required />
              <div className="flex flex-wrap gap-2">
                {["Jaipur 5 days ₹45,000", "Goa 4 days ₹38,000", "Paris 6 days $3000", "Tokyo 7 days $4000"].map(q => (
                  <button key={q} type="button"
                    className="text-xs px-2 py-1 rounded-full border hover:bg-blue-50 text-blue-700 border-blue-200"
                    onClick={() => setUserInput("Plan a trip to " + q + " for 2 people")}>
                    {q}
                  </button>
                ))}
              </div>
              <Button type="submit" className="w-full bg-blue-600 hover:bg-blue-700" disabled={loading || !user}>
                {loading
                  ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />{LOADING_STEPS[loadStep]}</>
                  : <><Plane className="mr-2 h-4 w-4" />Generate Travel Plan</>}
              </Button>
            </form>
            {error && <div className="mt-4 p-4 border border-red-200 rounded-lg text-red-600 text-sm">{error}</div>}
          </CardContent>
        </Card>
      )}

      {/* Results */}
      {travelPlan && (
        <div className="space-y-6">
          {/* Summary header */}
          <Card className="bg-gradient-to-r from-blue-600 to-indigo-700 text-white">
            <CardHeader>
              <CardTitle className="text-2xl text-white">{travelPlan.travel_details.destination}</CardTitle>
              <CardDescription className="text-blue-100">{travelPlan.travel_details.overview}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                  { label: "Duration",  val: travelPlan.travel_details.duration + " days" },
                  { label: "Budget",    val: fmt(travelPlan.travel_details.budget_inr)     },
                  { label: "Travelers", val: String(travelPlan.travel_details.travelers)   },
                  { label: "Type",      val: travelPlan.travel_details.travel_type         },
                ].map(i => (
                  <div key={i.label}>
                    <p className="text-xs text-blue-200">{i.label}</p>
                    <p className="text-lg font-bold text-white">{i.val}</p>
                  </div>
                ))}
                {travelPlan.travel_details.start_date && (
                  <div className="col-span-2">
                    <p className="text-xs text-blue-200">Trip Dates</p>
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
              <div className="flex items-center gap-2 p-3 bg-blue-50 rounded-lg text-sm text-blue-800 border border-blue-200">
                <RefreshCw className="h-4 w-4 shrink-0" />
                <span>Each day has a <strong>Re-optimize</strong> button — click it to swap the last attraction and regenerate that day in real time.</span>
              </div>
              {travelPlan.itinerary.map((day, i) => (
                <DayCard key={i} day={day} reoptLoading={reoptLoading}
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
