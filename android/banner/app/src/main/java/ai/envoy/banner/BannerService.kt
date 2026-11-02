package ai.envoy.banner

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.IBinder
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.LinearLayout
import android.widget.TextView

/**
 * A small pill at the top centre of the screen while Envoy works on this phone: "● Envoy is using this phone · Pause".
 *
 *   adb shell am start-foreground-service -n ai.envoy.banner/.BannerService -a ai.envoy.banner.SHOW --es text "…"
 *   adb shell am start-foreground-service -n ai.envoy.banner/.BannerService -a ai.envoy.banner.PAUSE --es reason "…"
 *   adb shell am start-foreground-service -n ai.envoy.banner/.BannerService -a ai.envoy.banner.RESUME
 *   adb shell am start-foreground-service -n ai.envoy.banner/.BannerService -a ai.envoy.banner.HIDE
 *   adb shell am start-foreground-service -n ai.envoy.banner/.BannerService -a ai.envoy.banner.ASIDE   (since version 2)
 *   adb shell am start-foreground-service -n ai.envoy.banner/.BannerService -a ai.envoy.banner.BACK    (since version 2)
 *
 * Pause and Resume on the pill change the state the Mac reads through StateProvider. The window never takes focus
 * (the keyboard stays with the app) and only the pill itself is touchable. ASIDE and BACK move the pill out of the way of
 * a tap Envoy makes under it and bring it back, leaving its state and the service as they are.
 *
 * Every start-foreground-service promises a startForeground() call, and Android 12+ crashes the app
 * (ForegroundServiceDidNotStartInTimeException, "Envoy banner keeps stopping") if the service is stopped while a start
 * still owes one. So the service is in the foreground from onCreate and on every command, and HIDE stops it only when
 * no later command has arrived (stopSelf(startId)): a HIDE and the next task's SHOW right behind it crashed the Pixel 5
 * twice on Nov 1, when plain stopSelf() brought the service down with the SHOW still pending.
 */
class BannerService : Service() {
    private var view: LinearLayout? = null
    private var label: TextView? = null
    private var button: TextView? = null
    private var text = "Envoy is using this phone"

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        startInForeground()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startInForeground()  // first, whatever the command: this start's promise is kept before anything else runs
        when (intent?.action) {
            ACTION_SHOW -> {
                text = intent.getStringExtra("text") ?: text
                State.set(this, paused = false, reason = "")
                show()
            }
            ACTION_PAUSE -> { State.set(this, paused = true, reason = intent.getStringExtra("reason") ?: "paused"); show() }
            ACTION_RESUME -> { State.set(this, paused = false, reason = ""); show() }
            ACTION_HIDE -> {
                hide()
                State.set(this, paused = false, reason = "", shown = false)
                stopWhenIdle(startId)
            }
            ACTION_ASIDE -> hide()
            ACTION_BACK -> if (State.shown(this)) show() else stopWhenIdle(startId)
            else -> show()
        }
        return START_NOT_STICKY
    }

    /** Out of the foreground and stopped, unless a command arrived after this one: that one still owes its startForeground(). */
    private fun stopWhenIdle(startId: Int) {
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf(startId)
    }

    override fun onDestroy() {
        hide()
        super.onDestroy()
    }

    private fun dp(v: Int) = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v.toFloat(), resources.displayMetrics).toInt()

    private fun startInForeground() {
        val nm = getSystemService(NotificationManager::class.java)
        if (nm.getNotificationChannel(CHANNEL) == null) {
            nm.createNotificationChannel(NotificationChannel(CHANNEL, "Envoy at work", NotificationManager.IMPORTANCE_LOW))
        }
        val n = Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("Envoy is using this phone")
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= 34) startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        else startForeground(1, n)
    }

    private fun show() {
        if (view == null) {
            val pill = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(dp(12), dp(6), dp(6), dp(6))
                background = GradientDrawable().apply { cornerRadius = dp(18).toFloat(); setColor(Color.argb(235, 28, 25, 23)) }
                elevation = dp(4).toFloat()
            }
            label = TextView(this).apply { setTextColor(Color.WHITE); textSize = 13f; maxLines = 1 }
            button = TextView(this).apply {
                setTextColor(Color.BLACK); textSize = 13f
                setPadding(dp(12), dp(4), dp(12), dp(4))
                background = GradientDrawable().apply { cornerRadius = dp(14).toFloat(); setColor(Color.WHITE) }
                setOnClickListener { State.set(this@BannerService, paused = !State.paused(this@BannerService), reason = "you pressed Pause on the phone"); render() }
            }
            pill.addView(label, LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply { marginEnd = dp(10) })
            pill.addView(button)
            val lp = WindowManager.LayoutParams(
                WindowManager.LayoutParams.WRAP_CONTENT, WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
                PixelFormat.TRANSLUCENT,
            ).apply { gravity = Gravity.TOP or Gravity.CENTER_HORIZONTAL; y = dp(2) }
            getSystemService(WindowManager::class.java).addView(pill, lp)
            view = pill
        }
        render()
    }

    private fun render() {
        val paused = State.paused(this)
        label?.text = if (paused) "● Envoy paused" else "● $text"
        button?.text = if (paused) "Resume" else "Pause"
        view?.visibility = View.VISIBLE
    }

    private fun hide() {
        view?.let { getSystemService(WindowManager::class.java).removeView(it) }
        view = null
    }

    companion object {
        const val CHANNEL = "envoy"
        const val ACTION_SHOW = "ai.envoy.banner.SHOW"
        const val ACTION_PAUSE = "ai.envoy.banner.PAUSE"
        const val ACTION_RESUME = "ai.envoy.banner.RESUME"
        const val ACTION_HIDE = "ai.envoy.banner.HIDE"
        const val ACTION_ASIDE = "ai.envoy.banner.ASIDE"
        const val ACTION_BACK = "ai.envoy.banner.BACK"
    }
}

/** Whether Envoy is paused on this phone, and since when (SharedPreferences, read by StateProvider). */
object State {
    private fun prefs(c: Context) = c.getSharedPreferences("state", Context.MODE_PRIVATE)
    fun paused(c: Context) = prefs(c).getBoolean("paused", false)
    fun shown(c: Context) = prefs(c).getBoolean("shown", false)
    fun set(c: Context, paused: Boolean, reason: String, shown: Boolean = true) {
        prefs(c).edit().putBoolean("paused", paused).putString("reason", reason).putBoolean("shown", shown)
            .putLong("changed_at", System.currentTimeMillis()).apply()
    }
    fun row(c: Context): Array<Any> = prefs(c).let {
        arrayOf(if (it.getBoolean("paused", false)) 1 else 0, it.getString("reason", "") ?: "", it.getLong("changed_at", 0L), if (it.getBoolean("shown", false)) 1 else 0)
    }
}
