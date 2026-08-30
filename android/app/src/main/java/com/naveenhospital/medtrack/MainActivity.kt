package com.naveenhospital.medtrack

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.compose.setContent
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.lifecycleScope
import com.naveenhospital.medtrack.core.push.MedtrackPush
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject
import kotlinx.coroutines.launch

@AndroidEntryPoint
class MainActivity : FragmentActivity() {
    @Inject lateinit var container: MedtrackAppContainer
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        if (intent.isMedtrackNotificationIntent()) {
            MedtrackPush.enqueueNotificationRefresh(this)
        }
        MedtrackPush.createChannels(this)
        setContent {
            MedtrackApp(
                container = container,
                onAuthenticated = {
                    container.startBackgroundSync()
                    enablePushForAuthenticatedSession()
                },
                notificationCaseId = null,
                onNotificationCaseConsumed = {},
            )
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (intent.isMedtrackNotificationIntent()) {
            MedtrackPush.enqueueNotificationRefresh(this)
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        // Never serialize the PHI navigation back stack or Compose saveable registry.
        // A recreated process must derive LOGIN/LOCK_SETUP/UNLOCK from the verified
        // encrypted session boundary instead of restoring a clinical destination.
        outState.clear()
    }

    private fun syncPushTokenIfConfigured() {
        MedtrackPush.fetchTokenIfConfigured(this) { token ->
            lifecycleScope.launch {
                MedtrackPush.registerTokenForCurrentSession(this@MainActivity, token)
            }
        }
    }

    private fun enablePushForAuthenticatedSession() {
        requestNotificationPermissionIfNeeded()
        syncPushTokenIfConfigured()
    }

    private fun requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) {
            return
        }
        ActivityCompat.requestPermissions(
            this,
            arrayOf(Manifest.permission.POST_NOTIFICATIONS),
            REQUEST_POST_NOTIFICATIONS,
        )
    }

    private companion object {
        const val REQUEST_POST_NOTIFICATIONS = 4001
    }
}

private fun Intent?.isMedtrackNotificationIntent(): Boolean {
    if (this == null) return false
    val keys = extras?.keySet().orEmpty()
    return keys.any { key ->
        key.startsWith("google.") ||
            key.startsWith("gcm.") ||
            key == "from" ||
            key == "message_type"
    }
}
