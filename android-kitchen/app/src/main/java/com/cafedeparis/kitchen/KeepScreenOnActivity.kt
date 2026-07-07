package com.cafedeparis.kitchen

import android.os.PowerManager
import android.view.View
import android.view.WindowManager
import androidx.appcompat.app.AppCompatActivity

/**
 * Keeps the display awake while the activity is in the foreground.
 * Uses window flags, view flags, and a screen wake lock for device compatibility.
 */
abstract class KeepScreenOnActivity : AppCompatActivity() {

    private var screenWakeLock: PowerManager.WakeLock? = null

    override fun setContentView(layoutResID: Int) {
        super.setContentView(layoutResID)
        applyKeepScreenOn(findViewById(android.R.id.content))
    }

    override fun setContentView(view: View) {
        super.setContentView(view)
        applyKeepScreenOn(view)
    }

    override fun onResume() {
        super.onResume()
        applyKeepScreenOn(findViewById(android.R.id.content))
        acquireScreenWakeLock()
    }

    override fun onPause() {
        releaseScreenWakeLock()
        super.onPause()
    }

    private fun applyKeepScreenOn(root: View?) {
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        window.decorView.keepScreenOn = true
        root?.keepScreenOn = true
    }

    @Suppress("DEPRECATION")
    private fun acquireScreenWakeLock() {
        if (screenWakeLock?.isHeld == true) return
        val powerManager = getSystemService(POWER_SERVICE) as PowerManager
        screenWakeLock = powerManager.newWakeLock(
            PowerManager.SCREEN_BRIGHT_WAKE_LOCK or PowerManager.ON_AFTER_RELEASE,
            "$packageName:keep_screen_on"
        ).apply {
            setReferenceCounted(false)
            acquire()
        }
    }

    private fun releaseScreenWakeLock() {
        screenWakeLock?.let { lock ->
            if (lock.isHeld) lock.release()
        }
        screenWakeLock = null
    }
}
