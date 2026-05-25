package com.naveenhospital.medtrack.core.push

import android.app.PendingIntent
import android.content.Intent
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import kotlin.math.absoluteValue
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
        MedtrackPush.createChannels(this)
        val title = message.notification?.title ?: message.data["title"] ?: "MEDTRACK"
        val body = message.notification?.body ?: message.data["body"] ?: "New update"
        val type = message.data["type"] ?: message.data["notification_type"]
        val caseId = message.data["case_id"] ?: message.data["caseId"]
        val channelId = MedtrackPush.channelForType(type)
        val launchIntent = packageManager.getLaunchIntentForPackage(packageName)
            ?.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
            ?.putExtra(EXTRA_CASE_ID, caseId)
            ?.putExtra(EXTRA_FROM_NOTIFICATION, true)
        val pendingIntent = launchIntent?.let {
            PendingIntent.getActivity(
                this,
                (message.messageId ?: caseId ?: "$title-$body").hashCode(),
                it,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
        }
        val smallIcon = applicationInfo.icon
        val notification = NotificationCompat.Builder(this, channelId)
            .setSmallIcon(smallIcon)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setAutoCancel(true)
            .setPriority(if (channelId == MedtrackPush.CHANNEL_OVERDUE) NotificationCompat.PRIORITY_DEFAULT else NotificationCompat.PRIORITY_HIGH)
            .apply {
                if (pendingIntent != null) {
                    setContentIntent(pendingIntent)
                }
            }
            .build()
        runCatching {
            NotificationManagerCompat.from(this).notify(
                (message.messageId ?: "$title-$body").hashCode().absoluteValue,
                notification,
            )
        }
    }

    override fun onDestroy() {
        serviceScope.cancel()
        super.onDestroy()
    }

    companion object {
        const val EXTRA_CASE_ID = "case_id"
        const val EXTRA_FROM_NOTIFICATION = "from_notification"
    }
}
