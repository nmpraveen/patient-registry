package com.naveenhospital.medtrack

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.compose.runtime.mutableStateOf
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.lifecycleScope
import com.naveenhospital.medtrack.core.push.MedtrackFirebaseMessagingService
import com.naveenhospital.medtrack.core.push.MedtrackPush
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject
import kotlinx.coroutines.launch

@AndroidEntryPoint
class MainActivity : FragmentActivity() {
    @Inject lateinit var container: MedtrackAppContainer
    private val notificationCaseId = mutableStateOf<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        notificationCaseId.value = intent.notificationCaseId()
        container.startBackgroundSync()
        MedtrackPush.createChannels(this)
        setContent {
            MedtrackApp(
                container = container,
                onAuthenticated = { enablePushForAuthenticatedSession() },
                notificationCaseId = notificationCaseId.value,
                onNotificationCaseConsumed = { notificationCaseId.value = null },
            )
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        notificationCaseId.value = intent.notificationCaseId()
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

private fun Intent?.notificationCaseId(): String? =
    this
        ?.takeIf { it.isMedtrackNotificationIntent() }
        ?.caseIdExtra()

private fun Intent.isMedtrackNotificationIntent(): Boolean {
    if (getBooleanExtra(MedtrackFirebaseMessagingService.EXTRA_FROM_NOTIFICATION, false)) {
        return true
    }
    val keys = extras?.keySet().orEmpty()
    return keys.any { key ->
        key.startsWith("google.") ||
            key.startsWith("gcm.") ||
            key == "from" ||
            key == "message_type"
    }
}

private fun Intent.caseIdExtra(): String? {
    return sequenceOf(
        getStringExtra(MedtrackFirebaseMessagingService.EXTRA_CASE_ID),
        getStringExtra("caseId"),
    ).firstNotNullOfOrNull { value ->
        value
            ?.trim()
            ?.takeUnless { it.isBlank() || it.equals("null", ignoreCase = true) || it.equals("none", ignoreCase = true) }
    }
}
