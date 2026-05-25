package com.naveenhospital.medtrack.feature.notifications

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.OpenInNew
import androidx.compose.material.icons.outlined.Assignment
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material.icons.outlined.Notifications
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.naveenhospital.medtrack.core.designsystem.MedtrackColors
import com.naveenhospital.medtrack.core.designsystem.MedtrackCompactCard
import com.naveenhospital.medtrack.core.designsystem.MedtrackIconBadge
import com.naveenhospital.medtrack.core.designsystem.MedtrackMiniPill
import com.naveenhospital.medtrack.core.designsystem.MedtrackSectionTitle
import com.naveenhospital.medtrack.core.domain.model.NotificationItem

@Composable
fun NotificationsScreen(
    notifications: List<NotificationItem>,
    isRefreshing: Boolean,
    error: String?,
    onRefresh: () -> Unit,
    onOpenNotification: (NotificationItem) -> Unit,
    modifier: Modifier = Modifier,
) {
    val unreadCount = notifications.count { !it.isRead }
    val criticalCount = notifications.count { !it.isRead && it.type in setOf("red_flag", "overdue") }
    val grouped = notifications.groupBy { it.groupLabel() }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(MedtrackColors.Surface)
            .padding(horizontal = 10.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("Notifications", color = MedtrackColors.Ink, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                Text("$unreadCount unread alerts", color = MedtrackColors.Muted, style = MaterialTheme.typography.labelMedium)
            }
            IconButton(onClick = onRefresh) {
                Icon(imageVector = Icons.Outlined.Refresh, contentDescription = "Refresh")
            }
        }

        error?.let { Text(text = it, color = MedtrackColors.Danger) }
        if (isRefreshing) {
            Text(text = "Refreshing", color = MedtrackColors.Muted)
        }

        if (criticalCount > 0) {
            Surface(
                shape = RoundedCornerShape(18.dp),
                color = MedtrackColors.DangerSoft,
                border = BorderStroke(1.dp, MedtrackColors.Danger.copy(alpha = 0.25f)),
            ) {
                Row(
                    modifier = Modifier.padding(12.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    MedtrackIconBadge(icon = Icons.Outlined.ErrorOutline, tint = MedtrackColors.Danger)
                    Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text("Needs attention", color = MedtrackColors.Danger, fontWeight = FontWeight.Bold)
                        Text("$criticalCount critical unread notification(s)", color = MedtrackColors.Danger, style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }

        if (notifications.isEmpty() && !isRefreshing) {
            MedtrackCompactCard {
                Text(text = "No notifications", color = MedtrackColors.Muted)
            }
        } else {
            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(9.dp),
                contentPadding = PaddingValues(bottom = 104.dp),
            ) {
                grouped.forEach { (group, items) ->
                    item(group) {
                        MedtrackSectionTitle(title = group, trailing = "${items.size}")
                    }
                    items(items, key = { it.id }) { item ->
                        NotificationRow(item = item, onOpenNotification = onOpenNotification)
                    }
                }
            }
        }
    }
}

@Composable
private fun NotificationRow(
    item: NotificationItem,
    onOpenNotification: (NotificationItem) -> Unit,
) {
    val color = item.typeColor()
    MedtrackCompactCard(
        modifier = if (item.caseId != null) Modifier.clickable { onOpenNotification(item) } else Modifier,
        borderColor = if (!item.isRead) color.copy(alpha = 0.38f) else MedtrackColors.Border,
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.Top, modifier = Modifier.fillMaxWidth()) {
            Box {
                MedtrackIconBadge(icon = item.typeIcon(), tint = color)
                if (!item.isRead) {
                    Surface(
                        modifier = Modifier
                            .align(Alignment.TopEnd)
                            .size(10.dp),
                        shape = RoundedCornerShape(50),
                        color = MedtrackColors.Danger,
                    ) {}
                }
            }
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = item.title,
                        color = MedtrackColors.Ink,
                        fontWeight = FontWeight.Bold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f),
                    )
                    MedtrackMiniPill(text = item.typeLabel(), color = color)
                }
                Text(
                    text = item.body,
                    color = MedtrackColors.Muted,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Text(text = item.createdAt.take(16), color = MedtrackColors.Muted, style = MaterialTheme.typography.labelSmall)
                    if (item.caseId != null) {
                        Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
                            Icon(imageVector = Icons.AutoMirrored.Outlined.OpenInNew, contentDescription = null, tint = MedtrackColors.Primary, modifier = Modifier.size(14.dp))
                            Text("Open case", color = MedtrackColors.Primary, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }
    }
}

private fun NotificationItem.groupLabel(): String =
    when (type) {
        "red_flag", "overdue" -> "Critical"
        "assignment" -> "Assignments"
        else -> "Updates"
    }

private fun NotificationItem.typeLabel(): String =
    when (type) {
        "red_flag" -> "Red"
        "overdue" -> "Overdue"
        "assignment" -> "Assigned"
        else -> "Info"
    }

private fun NotificationItem.typeColor(): Color =
    when (type) {
        "red_flag" -> MedtrackColors.Danger
        "overdue" -> MedtrackColors.Warning
        "assignment" -> MedtrackColors.Primary
        else -> MedtrackColors.Muted
    }

private fun NotificationItem.typeIcon() =
    when (type) {
        "assignment" -> Icons.Outlined.Assignment
        "red_flag", "overdue" -> Icons.Outlined.ErrorOutline
        else -> Icons.Outlined.Notifications
    }
