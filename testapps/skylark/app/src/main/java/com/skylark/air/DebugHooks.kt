package com.skylark.air

import android.content.BroadcastReceiver
import android.content.ContentProvider
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.database.Cursor
import android.database.MatrixCursor
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.util.Base64
import android.util.Log

/**
 * Test hooks used by Envoy's eval runner (explicit broadcasts, so they work on Android 8+):
 *
 *   adb shell am broadcast -n com.skylark.air/.DebugReceiver -a com.skylark.air.RESET
 *   adb shell am broadcast -n com.skylark.air/.DebugReceiver -a com.skylark.air.SEED --es json_b64 <base64 json>
 *   adb shell am broadcast -n com.skylark.air/.DebugReceiver -a com.skylark.air.VARIANT --ei variant 2
 *   adb shell am broadcast -n com.skylark.air/.DebugReceiver -a com.skylark.air.SET_GATE --es code KX7Q2M --es gate C14
 *   adb shell am broadcast -n com.skylark.air/.DebugReceiver -a com.skylark.air.SIGN_OUT
 *
 * Layout variants: 0 original, 1 moved button, 2 renamed labels, 3 extra confirmation screen.
 */
class DebugReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        Store.init(context.applicationContext)
        when (intent.action) {
            "com.skylark.air.RESET" -> Store.reset()
            "com.skylark.air.SEED" -> {
                val b64 = intent.getStringExtra("json_b64") ?: return fail("SEED needs json_b64")
                Store.seed(String(Base64.decode(b64, Base64.DEFAULT)))
            }
            "com.skylark.air.VARIANT" -> Store.setVariant(intent.getIntExtra("variant", 0))
            "com.skylark.air.SET_GATE" -> Store.setGate(
                intent.getStringExtra("code") ?: return fail("SET_GATE needs code"),
                intent.getStringExtra("gate") ?: return fail("SET_GATE needs gate"),
            )
            "com.skylark.air.SIGN_OUT" -> Store.signOut()
            else -> return fail("unknown action ${intent.action}")
        }
        resultCode = 0
        resultData = "ok"
    }

    private fun fail(message: String) {
        Log.w("SkyLarkDebug", message)
        resultCode = 1
        resultData = message
    }
}

/**
 * State hook: `adb shell content read --uri content://com.skylark.air.debug/state` prints the whole
 * state as JSON; `content query` returns flattened key/value rows.
 */
class StateProvider : ContentProvider() {
    override fun onCreate(): Boolean = true

    override fun openFile(uri: Uri, mode: String): ParcelFileDescriptor {
        Store.init(context!!.applicationContext)
        val (read, write) = ParcelFileDescriptor.createPipe()
        Thread {
            ParcelFileDescriptor.AutoCloseOutputStream(write).use { it.write(Store.json().toByteArray()) }
        }.start()
        return read
    }

    override fun query(uri: Uri, p: Array<out String>?, s: String?, a: Array<out String>?, o: String?): Cursor {
        Store.init(context!!.applicationContext)
        val st = Store.current
        val c = MatrixCursor(arrayOf("key", "value"))
        c.addRow(arrayOf("signed_in", st.signedIn.toString()))
        c.addRow(arrayOf("variant", st.variant.toString()))
        c.addRow(arrayOf("gate_alerts", st.profile.gateAlerts.toString()))
        c.addRow(arrayOf("miles", st.profile.miles.toString()))
        for (t in st.trips.filter { it.upcoming }) {
            c.addRow(arrayOf("${t.code}.checked_in", t.checkedIn.toString()))
            c.addRow(arrayOf("${t.code}.seat", t.flight.seat))
            c.addRow(arrayOf("${t.code}.gate", t.flight.gate))
            c.addRow(arrayOf("${t.code}.ktn", t.ktn))
            c.addRow(arrayOf("${t.code}.bags", t.bags.toString()))
            c.addRow(arrayOf("${t.code}.cancelled", t.cancelled.toString()))
        }
        return c
    }

    override fun getType(uri: Uri): String = "application/json"
    override fun insert(uri: Uri, values: ContentValues?): Uri? = null
    override fun delete(uri: Uri, s: String?, a: Array<out String>?): Int = 0
    override fun update(uri: Uri, v: ContentValues?, s: String?, a: Array<out String>?): Int = 0
}
