package com.naveenhospital.medtrack.core.push

import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import java.util.UUID
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

class MedtrackFirebaseMessagingService : FirebaseMessagingService() {
    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onNewToken(token: String) {
        super.onNewToken(token)
        serviceScope.launch {
            MedtrackPush.registerTokenForCurrentSession(this@MedtrackFirebaseMessagingService, token)
        }
    }

    override fun onMessageReceived(message: RemoteMessage) {
        super.onMessageReceived(message)
        val policy = policyForOpaquePush(
            untrustedData = message.data,
            untrustedTitle = message.notification?.title,
            untrustedBody = message.notification?.body,
            accountMatches = null,
            sessionAuthorized = false,
            networkAvailable = false,
        )
        if (policy.enqueueAuthenticatedRefresh) {
            MedtrackPush.enqueueNotificationRefresh(this)
        }
    }

    override fun onDestroy() {
        serviceScope.cancel()
        super.onDestroy()
    }
}

internal data class OpaquePushPolicy(
    val enqueueAuthenticatedRefresh: Boolean,
    val displaySystemNotification: Boolean,
    val forwardPayloadToIntent: Boolean,
)

/**
 * FCM is only an opaque wake-up signal. Raw push data never reaches a system notification or
 * intent. Account/session authorization must be proven by the authenticated sync path; until the
 * account-security lane supplies that identity generation, display remains suppressed.
 */
@Suppress("UNUSED_PARAMETER")
internal fun policyForOpaquePush(
    untrustedData: Map<String, String>,
    untrustedTitle: String?,
    untrustedBody: String?,
    accountMatches: Boolean?,
    sessionAuthorized: Boolean,
    networkAvailable: Boolean,
): OpaquePushPolicy {
    val hasExactDataOnlyEnvelope =
        untrustedTitle == null &&
            untrustedBody == null &&
            untrustedData.keys == setOf("event_id") &&
            untrustedData["event_id"].isUuid()
    return OpaquePushPolicy(
        enqueueAuthenticatedRefresh = hasExactDataOnlyEnvelope,
        displaySystemNotification = false,
        forwardPayloadToIntent = false,
    )
}

private fun String?.isUuid(): Boolean {
    val candidate = this ?: return false
    val canonical = runCatching { UUID.fromString(candidate).toString() }.getOrNull() ?: return false
    return canonical.equals(candidate, ignoreCase = true)
}
