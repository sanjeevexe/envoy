package com.skylark.air

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * All of SkyLark Air's state, as one JSON document.
 *
 * The app reads and writes it through [Store]; the debug hooks (DebugReceiver, StateProvider)
 * seed it, reset it, switch layout variants and expose it to tests, so success checks are exact.
 */
data class Flight(
    val number: String, val from: String, val to: String, val date: String,
    val depart: String, val arrive: String, val gate: String, val seat: String,
    val boarding: String, val group: String, val status: String,
)

data class Trip(
    val code: String, val city: String, val upcoming: Boolean, val checkinOpen: Boolean,
    val checkedIn: Boolean, val cancelled: Boolean, val ktn: String, val bags: Int, val flight: Flight,
)

data class Profile(
    val firstName: String, val lastName: String, val email: String, val phoneLast4: String,
    val rewardsNumber: String, val miles: Int, val tier: String, val gateAlerts: Boolean,
)

data class SeatMap(
    val firstRow: Int, val lastRow: Int, val paidRows: List<Int>, val paidPrice: Int, val occupied: Set<String>,
)

data class AppState(
    val signedIn: Boolean,
    val smsCode: String,
    val showRatingPrompt: Boolean,
    val variant: Int,
    val profile: Profile,
    val trips: List<Trip>,
    val seatMap: SeatMap,
) {
    fun trip(code: String): Trip? = trips.firstOrNull { it.code == code }
    val nextTrip: Trip? get() = trips.firstOrNull { it.upcoming && !it.cancelled }
}

// ---- JSON ---------------------------------------------------------------------------------------

private fun JSONObject.toFlight() = Flight(
    getString("number"), getString("from"), getString("to"), getString("date"), getString("depart"),
    getString("arrive"), getString("gate"), getString("seat"), getString("boarding"), getString("group"),
    getString("status"),
)

private fun Flight.toJson() = JSONObject()
    .put("number", number).put("from", from).put("to", to).put("date", date).put("depart", depart)
    .put("arrive", arrive).put("gate", gate).put("seat", seat).put("boarding", boarding)
    .put("group", group).put("status", status)

private fun JSONObject.toTrip() = Trip(
    getString("code"), getString("city"), getBoolean("upcoming"), optBoolean("checkin_open"),
    optBoolean("checked_in"), optBoolean("cancelled"), optString("ktn"), optInt("bags"),
    getJSONObject("flight").toFlight(),
)

private fun Trip.toJson() = JSONObject()
    .put("code", code).put("city", city).put("upcoming", upcoming).put("checkin_open", checkinOpen)
    .put("checked_in", checkedIn).put("cancelled", cancelled).put("ktn", ktn).put("bags", bags)
    .put("flight", flight.toJson())

fun parseState(json: String): AppState {
    val o = JSONObject(json)
    val p = o.getJSONObject("profile")
    val s = o.getJSONObject("seatmap")
    val trips = o.getJSONArray("trips")
    return AppState(
        signedIn = o.optBoolean("signed_in", true),
        smsCode = o.optString("sms_code", "482913"),
        showRatingPrompt = o.optBoolean("show_rating_prompt"),
        variant = o.optInt("variant"),
        profile = Profile(
            p.getString("first_name"), p.getString("last_name"), p.getString("email"),
            p.optString("phone_last4"), p.getString("rewards_number"), p.getInt("miles"),
            p.optString("tier"), p.optBoolean("gate_alerts"),
        ),
        trips = (0 until trips.length()).map { trips.getJSONObject(it).toTrip() },
        seatMap = SeatMap(
            s.getInt("first_row"), s.getInt("last_row"),
            s.getJSONArray("paid_rows").let { a -> (0 until a.length()).map { a.getInt(it) } },
            s.getInt("paid_price"),
            s.getJSONArray("occupied").let { a -> (0 until a.length()).map { a.getString(it) }.toSet() },
        ),
    )
}

fun AppState.toJson(): JSONObject = JSONObject()
    .put("signed_in", signedIn).put("sms_code", smsCode).put("show_rating_prompt", showRatingPrompt)
    .put("variant", variant)
    .put(
        "profile", JSONObject()
            .put("first_name", profile.firstName).put("last_name", profile.lastName)
            .put("email", profile.email).put("phone_last4", profile.phoneLast4)
            .put("rewards_number", profile.rewardsNumber).put("miles", profile.miles)
            .put("tier", profile.tier).put("gate_alerts", profile.gateAlerts),
    )
    .put("trips", JSONArray().apply { trips.forEach { put(it.toJson()) } })
    .put(
        "seatmap", JSONObject()
            .put("first_row", seatMap.firstRow).put("last_row", seatMap.lastRow)
            .put("paid_rows", JSONArray(seatMap.paidRows)).put("paid_price", seatMap.paidPrice)
            .put("occupied", JSONArray(seatMap.occupied.sorted())),
    )

// ---- Store --------------------------------------------------------------------------------------

object Store {
    private lateinit var file: File
    private lateinit var defaults: String
    private val _state = MutableStateFlow<AppState?>(null)
    val state: StateFlow<AppState?> = _state

    /** Bumped on every reset or seed so the UI returns to its start screen. */
    private val _epoch = MutableStateFlow(0)
    val epoch: StateFlow<Int> = _epoch

    @Synchronized
    fun init(context: Context) {
        if (_state.value != null) return
        file = File(context.filesDir, "state.json")
        defaults = context.assets.open("fixtures.json").bufferedReader().use { it.readText() }
        _state.value = runCatching { parseState(file.readText()) }.getOrElse { parseState(defaults) }
    }

    val current: AppState get() = _state.value!!

    @Synchronized
    private fun update(f: (AppState) -> AppState) {
        val next = f(current)
        _state.value = next
        file.writeText(next.toJson().toString(2))
    }

    fun json(): String = current.toJson().toString(2)

    // Debug hooks
    fun reset() { update { parseState(defaults) }; _epoch.value += 1 }
    fun seed(json: String) { update { parseState(json) }; _epoch.value += 1 }
    fun setVariant(v: Int) = update { it.copy(variant = v.coerceIn(0, 5)) }
    fun setGate(code: String, gate: String) = updateTrip(code) { it.copy(flight = it.flight.copy(gate = gate)) }
    fun signOut() { update { it.copy(signedIn = false) }; _epoch.value += 1 }

    // App actions
    fun signIn() = update { it.copy(signedIn = true) }
    fun dismissRatingPrompt() = update { it.copy(showRatingPrompt = false) }
    fun setGateAlerts(on: Boolean) = update { it.copy(profile = it.profile.copy(gateAlerts = on)) }
    fun checkIn(code: String) = updateTrip(code) { it.copy(checkedIn = true) }
    fun saveKtn(code: String, ktn: String) = updateTrip(code) { it.copy(ktn = ktn) }
    fun addBag(code: String) = updateTrip(code) { it.copy(bags = it.bags + 1) }
    fun cancelTrip(code: String) = updateTrip(code) { it.copy(cancelled = true) }

    fun changeSeat(code: String, seat: String) = update { s ->
        val trip = s.trip(code) ?: return@update s
        val freed = s.seatMap.occupied - seat
        s.copy(
            seatMap = s.seatMap.copy(occupied = freed),
            trips = s.trips.map { if (it.code == code) trip.copy(flight = trip.flight.copy(seat = seat)) else it },
        )
    }

    private fun updateTrip(code: String, f: (Trip) -> Trip) = update { s ->
        s.copy(trips = s.trips.map { if (it.code == code) f(it) else it })
    }
}
