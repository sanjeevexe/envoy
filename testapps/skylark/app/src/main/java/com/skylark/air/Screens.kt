package com.skylark.air

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.password
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.text.NumberFormat
import java.util.Locale

// ---- Shared pieces ------------------------------------------------------------------------------

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun Page(
    title: String,
    nav: Nav?,
    bottomBar: @Composable () -> Unit = {},
    content: @Composable () -> Unit,
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(title, Modifier.testTag("screen_title")) },
                navigationIcon = {
                    if (nav != null) {
                        IconButton(onClick = nav.back, modifier = Modifier.testTag("btn_back")) {
                            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                        }
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = SkyLarkBlue, titleContentColor = Color.White, navigationIconContentColor = Color.White),
            )
        },
        bottomBar = bottomBar,
    ) { padding ->
        Box(Modifier.padding(padding).fillMaxSize()) { content() }
    }
}

@Composable
private fun ScrollColumn(content: @Composable () -> Unit) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp).imePadding(),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) { content() }
}

@Composable
private fun InfoRow(label: String, value: String, tag: String) {
    Row(Modifier.fillMaxWidth().testTag(tag).semantics(mergeDescendants = true) {}, horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = Color.Gray)
        Text(value, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun CheckRow(text: String, checked: Boolean, tag: String, onChange: (Boolean) -> Unit) {
    Row(
        Modifier.fillMaxWidth().testTag(tag).toggleable(value = checked, role = Role.Checkbox, onValueChange = onChange).padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Checkbox(checked = checked, onCheckedChange = null)
        Spacer(Modifier.width(8.dp))
        Text(text)
    }
}

private fun miles(n: Int): String = NumberFormat.getIntegerInstance(Locale.US).format(n)

// ---- Sign-in ------------------------------------------------------------------------------------

@Composable
fun SignInScreen(s: AppState, nav: Nav) {
    var email by rememberSaveable { mutableStateOf("") }
    var password by rememberSaveable { mutableStateOf("") }
    var error by remember { mutableStateOf("") }
    Page("Sign in to SkyLark", null) {
        ScrollColumn {
            Text("Welcome back", fontSize = 24.sp, fontWeight = FontWeight.Bold)
            Text("Sign in to see your trips, check in and get your boarding pass.")
            OutlinedTextField(email, { email = it }, label = { Text("Email") }, singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email), modifier = Modifier.fillMaxWidth().testTag("field_email"))
            OutlinedTextField(password, { password = it }, label = { Text("Password") }, singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                modifier = Modifier.fillMaxWidth().testTag("field_password").semantics { password() })
            if (error.isNotEmpty()) Text(error, color = Color.Red, modifier = Modifier.testTag("text_error"))
            Button(onClick = {
                if (email.isBlank() || password.isBlank()) error = "Enter your email and password" else nav.push(Screen.SmsCode)
            }, modifier = Modifier.fillMaxWidth().testTag("btn_sign_in")) { Text("Sign in") }
        }
    }
}

@Composable
fun SmsCodeScreen(s: AppState, nav: Nav) {
    var code by rememberSaveable { mutableStateOf("") }
    var error by remember { mutableStateOf("") }
    Page("Verify it's you", nav) {
        ScrollColumn {
            Text("We texted a 6-digit code to (•••) •••-${s.profile.phoneLast4}.")
            OutlinedTextField(code, { code = it.filter(Char::isDigit).take(6) }, label = { Text("Verification code") }, singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                modifier = Modifier.fillMaxWidth().testTag("field_sms_code"))
            if (error.isNotEmpty()) Text(error, color = Color.Red, modifier = Modifier.testTag("text_error"))
            Button(onClick = {
                if (code == s.smsCode) { Store.signIn(); nav.resetTo(Screen.Tab(HomeTab.HOME)) } else error = "That code didn't work. Try again."
            }, modifier = Modifier.fillMaxWidth().testTag("btn_verify")) { Text("Verify") }
        }
    }
}

// ---- Tabs ---------------------------------------------------------------------------------------

@Composable
fun TabsScreen(s: AppState, nav: Nav, tab: HomeTab) {
    val order = if (s.variant == 1) listOf(HomeTab.STATUS, HomeTab.TRIPS, HomeTab.HOME, HomeTab.PROFILE)
    else listOf(HomeTab.HOME, HomeTab.TRIPS, HomeTab.STATUS, HomeTab.PROFILE)
    val title = when (tab) {
        HomeTab.HOME -> "SkyLark Air"
        HomeTab.TRIPS -> label(s, "My Trips")
        HomeTab.STATUS -> label(s, "Flight status")
        HomeTab.PROFILE -> "Profile"
    }
    Page(title, null, bottomBar = {
        NavigationBar {
            for (t in order) {
                val (text, icon, tag) = when (t) {
                    HomeTab.HOME -> Triple("Home", Icons.Filled.Home, "nav_home")
                    HomeTab.TRIPS -> Triple(label(s, "My Trips"), Icons.Filled.DateRange, "nav_trips")
                    HomeTab.STATUS -> Triple(label(s, "Flight status"), Icons.Filled.Search, "nav_status")
                    HomeTab.PROFILE -> Triple("Profile", Icons.Filled.Person, "nav_profile")
                }
                NavigationBarItem(
                    selected = t == tab, onClick = { nav.replace(Screen.Tab(t)) },
                    icon = { Icon(icon, contentDescription = null) }, label = { Text(text) },
                    modifier = Modifier.testTag(tag),
                )
            }
        }
    }) {
        when (tab) {
            HomeTab.HOME -> HomeTabContent(s, nav)
            HomeTab.TRIPS -> TripsTabContent(s, nav)
            HomeTab.STATUS -> StatusTabContent(s)
            HomeTab.PROFILE -> ProfileTabContent(s, nav)
        }
    }
    if (s.showRatingPrompt) {
        AlertDialog(
            onDismissRequest = { Store.dismissRatingPrompt() },
            title = { Text("Enjoying SkyLark?") },
            text = { Text("Tap a star to rate us on the Play Store.") },
            confirmButton = { TextButton(onClick = { Store.dismissRatingPrompt() }, Modifier.testTag("btn_rate_now")) { Text("Rate now") } },
            dismissButton = { TextButton(onClick = { Store.dismissRatingPrompt() }, Modifier.testTag("btn_not_now")) { Text("Not now") } },
        )
    }
}

@Composable
private fun HomeTabContent(s: AppState, nav: Nav) {
    var promo by rememberSaveable { mutableStateOf(true) }
    ScrollColumn {
        Text("Good morning, ${s.profile.firstName}", fontSize = 22.sp, fontWeight = FontWeight.Bold, modifier = Modifier.testTag("text_greeting"))
        val next = s.nextTrip
        if (next != null) {
            Card(Modifier.fillMaxWidth().testTag("card_next_trip").clickable { nav.push(Screen.TripDetails(next.code)) }) {
                Column(Modifier.padding(16.dp)) {
                    Text("Next trip", color = Color.Gray)
                    Text("${next.city} · ${next.flight.date}", fontWeight = FontWeight.Bold)
                    Text("${next.flight.number} · ${next.flight.from} ${next.flight.depart} → ${next.flight.to} ${next.flight.arrive}")
                }
            }
            if (s.variant != 1 && next.checkinOpen && !next.checkedIn) {
                Button(onClick = { nav.push(Screen.CheckIn(next.code, 0)) }, Modifier.fillMaxWidth().testTag("btn_home_checkin")) {
                    Text(label(s, "Check in"))
                }
            }
        } else {
            Text("No upcoming trips.")
        }
        if (promo) {
            Card(Modifier.fillMaxWidth().testTag("card_promo"), colors = CardDefaults.cardColors(containerColor = Color(0xFFFFF4D6))) {
                Column(Modifier.padding(16.dp)) {
                    Text("Double miles on fall flights", fontWeight = FontWeight.Bold)
                    Text("Book by Nov 15 and earn 2x SkyLark miles.")
                    TextButton(onClick = { promo = false }, Modifier.testTag("btn_dismiss_promo")) { Text("Dismiss") }
                }
            }
        }
        Text("SkyLark Rewards: ${miles(s.profile.miles)} miles", modifier = Modifier.testTag("text_home_miles"))
    }
}

@Composable
private fun TripsTabContent(s: AppState, nav: Nav) {
    var code by rememberSaveable { mutableStateOf("") }
    var last by rememberSaveable { mutableStateOf("") }
    var error by remember { mutableStateOf("") }
    val upcoming = s.trips.filter { it.upcoming && !it.cancelled }
    val past = s.trips.filter { !it.upcoming }
    LazyColumn(Modifier.fillMaxSize().imePadding().testTag("list_trips"), contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Find a trip", fontWeight = FontWeight.Bold)
                    OutlinedTextField(code, { code = it.uppercase().take(6) }, label = { Text("Confirmation code") }, singleLine = true,
                        modifier = Modifier.fillMaxWidth().testTag("field_confirmation"))
                    OutlinedTextField(last, { last = it }, label = { Text("Last name") }, singleLine = true,
                        modifier = Modifier.fillMaxWidth().testTag("field_last_name"))
                    if (error.isNotEmpty()) Text(error, color = Color.Red, modifier = Modifier.testTag("text_error"))
                    Button(onClick = {
                        val t = s.trip(code.trim())
                        if (t != null && last.trim().equals(s.profile.lastName, ignoreCase = true)) { error = ""; nav.push(Screen.TripDetails(t.code)) }
                        else error = "We couldn't find a trip with that code and last name."
                    }, Modifier.fillMaxWidth().testTag("btn_find_trip")) { Text(label(s, "Find trip")) }
                }
            }
        }
        item { Text("Upcoming", fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 8.dp)) }
        items(upcoming, key = { it.code }) { TripRow(it, nav) }
        item { Text("Past trips", fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 8.dp)) }
        items(past, key = { it.code }) { TripRow(it, nav) }
    }
}

@Composable
private fun TripRow(t: Trip, nav: Nav) {
    Card(Modifier.fillMaxWidth().testTag("trip_row_${t.code}").clickable { nav.push(Screen.TripDetails(t.code)) }) {
        Column(Modifier.padding(14.dp)) {
            Text("${t.city} · ${t.flight.date}", fontWeight = FontWeight.SemiBold)
            Text("${t.flight.number} · ${t.flight.from} → ${t.flight.to} · ${t.code}", color = Color.DarkGray)
        }
    }
}

@Composable
private fun StatusTabContent(s: AppState) {
    var query by rememberSaveable { mutableStateOf("") }
    var result by remember { mutableStateOf<String?>(null) }
    ScrollColumn {
        Text("Check any SkyLark flight", fontWeight = FontWeight.Bold)
        OutlinedTextField(query, { query = it }, label = { Text("Flight number") }, singleLine = true,
            modifier = Modifier.fillMaxWidth().testTag("field_flight_number"))
        Button(onClick = {
            val digits = query.filter(Char::isDigit)
            val f = s.trips.map { it.flight }.firstOrNull { it.number.filter(Char::isDigit) == digits && digits.isNotEmpty() }
            result = if (f == null) "No SkyLark flight found for \"$query\"."
            else "${f.number} · ${f.from} → ${f.to} · ${f.date} · ${f.status} · Gate ${f.gate} · Departs ${f.depart}"
        }, Modifier.fillMaxWidth().testTag("btn_search_status")) { Text("Search") }
        result?.let { Text(it, modifier = Modifier.testTag("text_status_result")) }
    }
}

@Composable
private fun ProfileTabContent(s: AppState, nav: Nav) {
    ScrollColumn {
        Text("${s.profile.firstName} ${s.profile.lastName}", fontSize = 22.sp, fontWeight = FontWeight.Bold, modifier = Modifier.testTag("text_name"))
        InfoRow("SkyLark Rewards", s.profile.rewardsNumber, "row_rewards_number")
        InfoRow("Status", s.profile.tier, "row_tier")
        InfoRow("Miles balance", "${miles(s.profile.miles)} miles", "row_miles")
        InfoRow("Email", s.profile.email, "row_email")
        HorizontalDivider()
        Row(
            Modifier.fillMaxWidth().testTag("switch_gate_alerts")
                .toggleable(value = s.profile.gateAlerts, role = Role.Switch, onValueChange = { Store.setGateAlerts(it) })
                .padding(vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column(Modifier.weight(1f)) {
                Text("Gate change alerts")
                Text("Get a notification when your gate changes.", color = Color.Gray, fontSize = 13.sp)
            }
            Switch(checked = s.profile.gateAlerts, onCheckedChange = null)
        }
        HorizontalDivider()
        OutlinedButton(onClick = { Store.signOut() }, Modifier.fillMaxWidth().testTag("btn_sign_out")) { Text("Sign out") }
    }
}

// ---- Trip details -------------------------------------------------------------------------------

@Composable
fun TripDetailsScreen(s: AppState, nav: Nav, code: String) {
    val t = s.trip(code) ?: return Page("Trip not found", nav) { Text("This trip no longer exists.") }
    var ktn by rememberSaveable(code) { mutableStateOf(t.ktn) }
    var saved by remember { mutableStateOf(false) }
    var confirmBag by remember { mutableStateOf(false) }
    var confirmCancel by remember { mutableStateOf(false) }
    val canCheckIn = t.upcoming && t.checkinOpen && !t.checkedIn && !t.cancelled
    val checkInButton = @Composable {
        Button(onClick = { nav.push(Screen.CheckIn(code, 0)) }, Modifier.fillMaxWidth().testTag("btn_checkin")) { Text(label(s, "Check in")) }
    }
    Page("Trip to ${t.city}", nav, bottomBar = {
        if (s.variant == 1 && canCheckIn) Box(Modifier.fillMaxWidth().padding(16.dp)) { checkInButton() }
    }) {
        ScrollColumn {
            Text("${t.flight.number} · ${t.flight.from} ${t.flight.depart} → ${t.flight.to} ${t.flight.arrive}", fontWeight = FontWeight.Bold, modifier = Modifier.testTag("text_flight"))
            InfoRow("Date", t.flight.date, "row_date")
            InfoRow("Confirmation", t.code, "row_confirmation")
            InfoRow("Status", if (t.cancelled) "Cancelled" else t.flight.status, "row_status")
            InfoRow("Gate", t.flight.gate, "row_gate")
            InfoRow("Seat", t.flight.seat, "row_seat")
            InfoRow("Boarding", "${t.flight.boarding} · Group ${t.flight.group}", "row_boarding")
            InfoRow("Checked bags", t.bags.toString(), "row_bags")
            if (t.checkedIn) {
                Text("You're checked in", color = Color(0xFF1B7F3B), fontWeight = FontWeight.Bold, modifier = Modifier.testTag("text_checked_in"))
                OutlinedButton(onClick = { nav.push(Screen.BoardingPass(code)) }, Modifier.fillMaxWidth().testTag("btn_boarding_pass")) { Text("View boarding pass") }
            }
            if (t.upcoming && !t.cancelled) {
                if (s.variant != 1 && canCheckIn) checkInButton()
                if (!t.checkinOpen && !t.checkedIn) Text("Check-in opens 24 hours before departure.", color = Color.Gray, modifier = Modifier.testTag("text_checkin_closed"))
                OutlinedButton(onClick = { nav.push(Screen.Seats(code)) }, Modifier.fillMaxWidth().testTag("btn_change_seat")) { Text(label(s, "Change seat")) }
                HorizontalDivider()
                Text("Known traveler number", fontWeight = FontWeight.SemiBold)
                OutlinedTextField(ktn, { ktn = it.filter(Char::isLetterOrDigit).take(12); saved = false }, label = { Text("Known traveler number") }, singleLine = true,
                    modifier = Modifier.fillMaxWidth().testTag("field_ktn"))
                Button(onClick = { Store.saveKtn(code, ktn); saved = true }, Modifier.fillMaxWidth().testTag("btn_save_ktn")) { Text("Save") }
                if (saved) Text("Known traveler number saved", color = Color(0xFF1B7F3B), modifier = Modifier.testTag("text_ktn_saved"))
                HorizontalDivider()
                OutlinedButton(onClick = { confirmBag = true }, Modifier.fillMaxWidth().testTag("btn_add_bag")) { Text("Add a checked bag ($35)") }
                TextButton(onClick = { confirmCancel = true }, Modifier.fillMaxWidth().testTag("btn_cancel_trip")) { Text("Cancel trip", color = Color.Red) }
            }
        }
    }
    if (confirmBag) AlertDialog(
        onDismissRequest = { confirmBag = false },
        title = { Text("Add a checked bag?") },
        text = { Text("Your card ending in 4242 will be charged $35.00.") },
        confirmButton = { TextButton(onClick = { Store.addBag(code); confirmBag = false }, Modifier.testTag("btn_pay_bag")) { Text("Pay $35") } },
        dismissButton = { TextButton(onClick = { confirmBag = false }, Modifier.testTag("btn_dialog_cancel")) { Text("Cancel") } },
    )
    if (confirmCancel) AlertDialog(
        onDismissRequest = { confirmCancel = false },
        title = { Text("Cancel this trip?") },
        text = { Text("This cancels ${t.flight.number} to ${t.city}. This can't be undone.") },
        confirmButton = { TextButton(onClick = { Store.cancelTrip(code); confirmCancel = false; nav.back() }, Modifier.testTag("btn_confirm_cancel")) { Text("Cancel trip") } },
        dismissButton = { TextButton(onClick = { confirmCancel = false }, Modifier.testTag("btn_keep_trip")) { Text("Keep trip") } },
    )
}

// ---- Check-in flow ------------------------------------------------------------------------------

private enum class CheckInStep { PASSENGERS, SAFETY, REVIEW, CONFIRM }

private fun checkInSteps(s: AppState) =
    if (s.variant == 3) listOf(CheckInStep.PASSENGERS, CheckInStep.SAFETY, CheckInStep.REVIEW, CheckInStep.CONFIRM)
    else listOf(CheckInStep.PASSENGERS, CheckInStep.SAFETY, CheckInStep.CONFIRM)

@Composable
fun CheckInScreen(s: AppState, nav: Nav, code: String, step: Int) {
    val t = s.trip(code) ?: return
    val steps = checkInSteps(s)
    val current = steps[step.coerceIn(0, steps.lastIndex)]
    val next = { nav.replace(Screen.CheckIn(code, step + 1)) }
    var passenger by rememberSaveable(code) { mutableStateOf(false) }
    var hazmat by rememberSaveable(code) { mutableStateOf(false) }
    Page("Check in · ${t.flight.number}", nav) {
        ScrollColumn {
            Text("Step ${step + 1} of ${steps.size}", color = Color.Gray, modifier = Modifier.testTag("text_step"))
            when (current) {
                CheckInStep.PASSENGERS -> {
                    Text("Who's checking in?", fontSize = 20.sp, fontWeight = FontWeight.Bold)
                    CheckRow("${s.profile.firstName} ${s.profile.lastName}", passenger, "cb_passenger_0") { passenger = it }
                    Button(onClick = next, enabled = passenger, modifier = Modifier.fillMaxWidth().testTag("btn_continue")) { Text(label(s, "Continue")) }
                }
                CheckInStep.SAFETY -> {
                    Text("Travel safety", fontSize = 20.sp, fontWeight = FontWeight.Bold)
                    Text("Lithium batteries, fireworks, flammable liquids and other hazardous materials are not allowed in checked or carry-on bags.")
                    CheckRow("I'm not carrying hazardous materials", hazmat, "cb_hazmat") { hazmat = it }
                    Button(onClick = next, enabled = hazmat, modifier = Modifier.fillMaxWidth().testTag("btn_continue")) { Text(label(s, "Continue")) }
                }
                CheckInStep.REVIEW -> {
                    Text("Review your trip", fontSize = 20.sp, fontWeight = FontWeight.Bold)
                    InfoRow("Flight", "${t.flight.number} · ${t.flight.from} → ${t.flight.to}", "row_review_flight")
                    InfoRow("Date", t.flight.date, "row_review_date")
                    InfoRow("Seat", t.flight.seat, "row_review_seat")
                    Button(onClick = next, modifier = Modifier.fillMaxWidth().testTag("btn_looks_good")) { Text("Looks good") }
                }
                CheckInStep.CONFIRM -> {
                    Text("Confirm check-in", fontSize = 20.sp, fontWeight = FontWeight.Bold)
                    InfoRow("Passenger", "${s.profile.firstName} ${s.profile.lastName}", "row_confirm_passenger")
                    InfoRow("Flight", "${t.flight.number} · ${t.flight.date}", "row_confirm_flight")
                    InfoRow("Seat", t.flight.seat, "row_confirm_seat")
                    Button(onClick = { Store.checkIn(code); nav.replace(Screen.BoardingPass(code)) }, Modifier.fillMaxWidth().testTag("btn_confirm_checkin")) {
                        Text(label(s, "Confirm check-in"))
                    }
                }
            }
        }
    }
}

@Composable
fun BoardingPassScreen(s: AppState, nav: Nav, code: String) {
    val t = s.trip(code) ?: return
    Page("Boarding pass", nav) {
        ScrollColumn {
            Text("You're checked in", fontSize = 22.sp, fontWeight = FontWeight.Bold, color = Color(0xFF1B7F3B), modifier = Modifier.testTag("text_checked_in"))
            Text("${s.profile.firstName} ${s.profile.lastName}", fontWeight = FontWeight.SemiBold)
            InfoRow("Flight", "${t.flight.number} · ${t.flight.from} → ${t.flight.to}", "row_bp_flight")
            InfoRow("Date", t.flight.date, "row_bp_date")
            InfoRow("Seat", t.flight.seat, "row_bp_seat")
            InfoRow("Gate", t.flight.gate, "row_bp_gate")
            InfoRow("Boarding", "${t.flight.boarding} · Group ${t.flight.group}", "row_bp_boarding")
            // A drawn barcode: no text in the tree, like real boarding passes.
            Box(Modifier.fillMaxWidth().height(160.dp).background(Color.White).border(1.dp, Color.Black).testTag("img_barcode")
                .semantics { contentDescription = "Boarding pass barcode" }) {
                Row(Modifier.fillMaxSize().padding(12.dp), horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                    for (i in 0 until 40) Box(Modifier.width(if (i % 3 == 0) 6.dp else 3.dp).fillMaxSize().background(Color.Black))
                }
            }
            Button(onClick = nav.home, Modifier.fillMaxWidth().testTag("btn_done")) { Text("Done") }
        }
    }
}

// ---- Seat map -----------------------------------------------------------------------------------

@Composable
fun SeatMapScreen(s: AppState, nav: Nav, code: String) {
    val t = s.trip(code) ?: return
    var selected by rememberSaveable(code) { mutableStateOf<String?>(null) }
    var message by remember { mutableStateOf("") }
    val letters = listOf("A", "B", "C", "D", "E", "F")
    val sm = s.seatMap
    val paid = selected?.let { seat -> seat.dropLast(1).toIntOrNull() in sm.paidRows } == true
    Page("Choose a seat · ${t.flight.number}", nav, bottomBar = {
        Column(Modifier.fillMaxWidth().background(Color(0xFFF3F6FA)).padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(if (selected == null) "Your seat: ${t.flight.seat}. Tap a seat to change it." else "Selected: $selected", modifier = Modifier.testTag("text_seat_selection"))
            if (message.isNotEmpty()) Text(message, color = Color(0xFF1B7F3B), modifier = Modifier.testTag("text_seat_message"))
            if (selected != null) {
                if (paid) Button(onClick = { Store.changeSeat(code, selected!!); message = "Seat changed to $selected"; selected = null },
                    Modifier.fillMaxWidth().testTag("btn_pay_seat")) { Text("Pay $${sm.paidPrice} and confirm") }
                else Button(onClick = { Store.changeSeat(code, selected!!); message = "Seat changed to $selected"; selected = null },
                    Modifier.fillMaxWidth().testTag("btn_confirm_seat")) { Text("Confirm seat") }
            }
        }
    }) {
        LazyColumn(Modifier.fillMaxSize().testTag("list_seats"), contentPadding = androidx.compose.foundation.layout.PaddingValues(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            item { Text("A and F are windows. C and D are aisles. Rows ${sm.paidRows.joinToString(" and ")} have extra legroom for $${sm.paidPrice}.", color = Color.Gray) }
            items((sm.firstRow..sm.lastRow).toList()) { row ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
                    Text("$row", Modifier.width(32.dp), color = Color.Gray)
                    for ((i, letter) in letters.withIndex()) {
                        if (i == 3) Spacer(Modifier.width(20.dp))
                        val seat = "$row$letter"
                        val mine = seat == t.flight.seat
                        val taken = seat in sm.occupied && !mine
                        val kind = when (letter) { "A", "F" -> "window"; "C", "D" -> "aisle"; else -> "middle" }
                        val extra = if (row in sm.paidRows) ", extra legroom $${sm.paidPrice}" else ""
                        val state = when { mine -> "your seat"; taken -> "occupied"; else -> "available" }
                        val color = when { mine -> SkyLarkBlue; seat == selected -> Color(0xFF2E9E57); taken -> Color(0xFFBDBDBD); row in sm.paidRows -> Color(0xFFF2C14E); else -> Color(0xFFDCE8F5) }
                        Box(
                            Modifier.padding(3.dp).size(40.dp).background(color, RoundedCornerShape(6.dp)).testTag("seat_$seat")
                                .semantics(mergeDescendants = true) { contentDescription = "Seat $seat, $kind$extra, $state" }
                                .clickable(enabled = !taken && !mine) { selected = seat; message = "" },
                            contentAlignment = Alignment.Center,
                        ) { Text(letter, fontSize = 12.sp, color = if (mine) Color.White else Color.Black) }
                    }
                }
            }
        }
    }
}
