package com.skylark.air

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.remember
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Store.init(applicationContext)
        setContent { SkyLarkApp() }
    }
}

/** Screens. Tabs are the roots; everything else is pushed on a simple back stack. */
sealed interface Screen {
    data object SignIn : Screen
    data object SmsCode : Screen
    data class Tab(val tab: HomeTab) : Screen
    data class TripDetails(val code: String) : Screen
    data class CheckIn(val code: String, val step: Int) : Screen
    data class BoardingPass(val code: String) : Screen
    data class Seats(val code: String) : Screen
}

enum class HomeTab { HOME, TRIPS, STATUS, PROFILE }

val SkyLarkBlue = Color(0xFF0B4F8A)

@OptIn(ExperimentalComposeUiApi::class)
@Composable
fun SkyLarkApp() {
    val state by Store.state.collectAsState()
    val epoch by Store.epoch.collectAsState()
    val s = state ?: return
    val stack = remember { mutableStateListOf<Screen>() }

    fun start(): Screen = if (s.signedIn) Screen.Tab(HomeTab.HOME) else Screen.SignIn
    LaunchedEffect(epoch) { stack.clear(); stack.add(start()) }
    if (stack.isEmpty()) stack.add(start())

    val nav = Nav(
        push = { stack.add(it) },
        replace = { stack[stack.lastIndex] = it },
        back = { if (stack.size > 1) stack.removeAt(stack.lastIndex) },
        home = { stack.clear(); stack.add(Screen.Tab(HomeTab.HOME)) },
        resetTo = { stack.clear(); stack.add(it) },
    )
    BackHandler(enabled = stack.size > 1) { nav.back() }

    MaterialTheme(colorScheme = lightColorScheme(primary = SkyLarkBlue)) {
        Surface(Modifier.fillMaxSize().semantics { testTagsAsResourceId = s.showsIds }) {
            Box(Modifier.fillMaxSize()) {
                when (val screen = stack.last()) {
                    Screen.SignIn -> SignInScreen(s, nav)
                    Screen.SmsCode -> SmsCodeScreen(s, nav)
                    is Screen.Tab -> TabsScreen(s, nav, screen.tab)
                    is Screen.TripDetails -> TripDetailsScreen(s, nav, screen.code)
                    is Screen.CheckIn -> CheckInScreen(s, nav, screen.code, screen.step)
                    is Screen.BoardingPass -> BoardingPassScreen(s, nav, screen.code)
                    is Screen.Seats -> SeatMapScreen(s, nav, screen.code)
                }
            }
        }
    }
}

class Nav(
    val push: (Screen) -> Unit,
    val replace: (Screen) -> Unit,
    val back: () -> Unit,
    val home: () -> Unit,
    val resetTo: (Screen) -> Unit,
)

/** Variants 2 and 5 rename labels; everything else keeps the original text. */
private val renames = mapOf(
    "Check in" to "Check-in now",
    "My Trips" to "Trips",
    "Change seat" to "Seats",
    "Continue" to "Next",
    "Confirm check-in" to "Complete check-in",
    "Flight status" to "Status",
    "Find trip" to "Look up",
)

fun label(s: AppState, original: String): String = if (s.variant == 2 || s.variant == 5) renames[original] ?: original else original

/** Variants 4 and 5 hide the test tags, like a release build with obfuscated resource IDs. */
val AppState.showsIds: Boolean get() = variant != 4 && variant != 5
