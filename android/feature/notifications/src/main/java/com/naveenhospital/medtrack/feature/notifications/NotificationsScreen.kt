package com.naveenhospital.medtrack.feature.notifications

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Assignment
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material.icons.outlined.ChevronRight
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material.icons.outlined.KeyboardArrowRight
import androidx.compose.material.icons.outlined.Notifications
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.WarningAmber
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.naveenhospital.medtrack.core.designsystem.MedtrackColors
import com.naveenhospital.medtrack.core.designsystem.MedtrackCompactCard
import com.naveenhospital.medtrack.core.designsystem.MedtrackIconBadge
import com.naveenhospital.medtrack.core.designsystem.MedtrackSectionEyebrow
import com.naveenhospital.medtrack.core.designsystem.medtrackTimestampLabel
import com.naveenhospital.medtrack.core.domain.model.NotificationItem

@Composable
fun NotificationsScreen(
    notifications: List<NotificationItem>,
    isRefreshing: Boolean,
    error: String?,
    onRefresh: () -> Unit,
    onOpenNotification: (NotificationItem) -> Unit,
    modifier: Modifier = Modifier,
    filterType: String? = null,
) {
    // When opened from a Me-page category row, scope to that notification type.
    val scopedNotifications = if (filterType != null) notifications.filter { it.type == filterType } else notifications
    var criticalOnly by rememberSaveable { mutableStateOf(false) }
    val unreadCount = scopedNotifications.count { !it.isRead }
    val criticalCount = if (filterType == null) scopedNotifications.count { it.type == "red_flag" } else 0
    val visibleNotifications = if (criticalOnly && filterType == null) {
        scopedNotifications.filter { it.type == "red_flag" }
    } else {
        scopedNotifications
    }
    val grouped = visibleNotifications
        .sortedWith(
            compareBy<NotificationItem> { it.groupPriority() }
                .thenBy { if (it.isRead) 1 else 0 }
                .thenByDescending { it.createdAt },
        )
        .groupBy { it.groupLabel() }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(MedtrackColors.Surface)
            .padding(horizontal = 10.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    text = filterType?.let(::notificationTypeTitle) ?: "Notifications",
                    color = MedtrackColors.Ink,
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.ExtraBold,
                )
                Text(
                    text = when {
                        filterType != null -> "$unreadCount unread · ${scopedNotifications.size} total"
                        criticalOnly -> "${visibleNotifications.size} red flags shown"
                        else -> "$unreadCount unread · $criticalCount critical"
                    },
                    color = MedtrackColors.Muted,
                    style = MaterialTheme.typography.labelSmall,
                )
            }
            NotificationHeaderIconButton(onClick = onRefresh)
        }

        error?.let { Text(text = it, color = MedtrackColors.Danger) }
        if (isRefreshing) {
            Text(text = "Refreshing", color = MedtrackColors.Muted)
        }

        if (criticalCount > 0) {
            Surface(
                modifier = Modifier.clickable { criticalOnly = !criticalOnly },
                shape = RoundedCornerShape(14.dp),
                color = MedtrackColors.DangerSoft.copy(alpha = 0.72f),
                border = BorderStroke(1.dp, MedtrackColors.DangerLine),
            ) {
                Row(
                    modifier = Modifier.padding(horizontal = 11.dp, vertical = 9.dp),
                    horizontalArrangement = Arrangement.spacedBy(9.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(
                        imageVector = Icons.Outlined.ErrorOutline,
                        contentDescription = null,
                        tint = MedtrackColors.Danger,
                        modifier = Modifier.size(22.dp),
                    )
                    Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(
                            "$criticalCount critical alerts need attention",
                            color = MedtrackColors.Danger,
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.ExtraBold,
                        )
                        Text(
                            if (criticalOnly) "Showing red-flag alerts" else "Tap to triage red-flag patients first",
                            color = MedtrackColors.Danger,
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.SemiBold,
                        )
                    }
                    Icon(imageVector = Icons.Outlined.ChevronRight, contentDescription = null, tint = MedtrackColors.Danger, modifier = Modifier.size(20.dp))
                }
            }
        }

        if (visibleNotifications.isEmpty() && !isRefreshing) {
            MedtrackCompactCard {
                Text(text = if (criticalOnly) "No critical notifications" else "No notifications", color = MedtrackColors.Muted)
                if (criticalOnly) {
                    TextButton(onClick = { criticalOnly = false }) {
                        Text("Show all")
                    }
                }
            }
        } else {
            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(8.dp),
                contentPadding = PaddingValues(bottom = 104.dp),
            ) {
                grouped.forEach { (group, items) ->
                    item(group) {
                        MedtrackSectionEyebrow(title = group, trailing = "${items.size}")
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
    val title = item.displayTitle()
    val body = item.displayBody(title)
    val isCritical = item.type == "red_flag"
    Surface(
        modifier = (if (item.caseId != null) Modifier.clickable { onOpenNotification(item) } else Modifier)
            .fillMaxWidth(),
        shape = RoundedCornerShape(15.dp),
        color = Color.White,
        border = BorderStroke(1.dp, if (!item.isRead) color.copy(alpha = if (isCritical) 0.32f else 0.24f) else MedtrackColors.Border),
        tonalElevation = 0.dp,
        shadowElevation = 1.dp,
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            if (isCritical) {
                Box(
                    modifier = Modifier
                        .width(3.dp)
                        .height(76.dp)
                        .background(color.copy(alpha = 0.9f), RoundedCornerShape(50)),
                )
            } else {
                Spacer(modifier = Modifier.width(4.dp))
            }
            Row(
                horizontalArrangement = Arrangement.spacedBy(9.dp),
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier
                    .weight(1f)
                    .padding(horizontal = 10.dp, vertical = 9.dp),
            ) {
            Box {
                MedtrackIconBadge(icon = item.typeIcon(), tint = color, modifier = Modifier.size(32.dp))
                if (!item.isRead) {
                    Surface(
                        modifier = Modifier
                            .align(Alignment.TopEnd)
                            .size(8.dp),
                        shape = RoundedCornerShape(50),
                        color = MedtrackColors.Danger,
                    ) {}
                }
            }
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = title,
                        color = MedtrackColors.Ink,
                        fontWeight = FontWeight.ExtraBold,
                        style = MaterialTheme.typography.titleSmall,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f),
                    )
                    NotificationTypePill(text = item.typeLabel(), color = color)
                }
                Text(
                    text = body,
                    color = MedtrackColors.Muted,
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 3.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(text = medtrackTimestampLabel(item.createdAt) ?: item.createdAt, color = MedtrackColors.Faint, style = MaterialTheme.typography.labelSmall)
                    if (item.caseId != null) {
                        Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
                            Text("Open alert", color = MedtrackColors.Primary, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold)
                            Icon(imageVector = Icons.Outlined.KeyboardArrowRight, contentDescription = null, tint = MedtrackColors.Primary, modifier = Modifier.size(15.dp))
                        }
                    }
                }
            }
            }
        }
    }
}

@Composable
private fun NotificationHeaderIconButton(onClick: () -> Unit) {
    Surface(
        modifier = Modifier
            .size(42.dp)
            .clickable(onClick = onClick),
        shape = RoundedCornerShape(12.dp),
        color = MedtrackColors.Card,
        border = BorderStroke(1.dp, MedtrackColors.Border),
        tonalElevation = 1.dp,
    ) {
        Box(contentAlignment = Alignment.Center) {
            Icon(imageVector = Icons.Outlined.Refresh, contentDescription = "Refresh", tint = MedtrackColors.Ink, modifier = Modifier.size(20.dp))
        }
    }
}

@Composable
private fun NotificationTypePill(text: String, color: Color) {
    Surface(
        shape = RoundedCornerShape(6.dp),
        color = color.copy(alpha = 0.10f),
        border = BorderStroke(1.dp, color.copy(alpha = 0.22f)),
    ) {
        Text(
            text = text.uppercase(),
            modifier = Modifier.padding(horizontal = 6.dp, vertical = 1.dp),
            color = color,
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.ExtraBold,
            maxLines = 1,
        )
    }
}

fun notificationTypeTitle(type: String): String =
    when (type) {
        "red_flag" -> "Red flags"
        "assignment" -> "Assignments"
        "overdue" -> "Overdue tasks"
        else -> "Notifications"
    }

private fun NotificationItem.groupLabel(): String =
    when (type) {
        "red_flag", "overdue" -> "Critical · Today"
        "assignment" -> "Assignments"
        else -> "Updates"
    }

private fun NotificationItem.groupPriority(): Int =
    when (type) {
        "red_flag", "overdue" -> 0
        "assignment" -> 1
        else -> 2
    }

private fun NotificationItem.typeLabel(): String =
    when (type) {
        "red_flag" -> "RED FLAG"
        "overdue" -> "OVERDUE TASK"
        "assignment" -> "ASSIGNED"
        else -> "INFO"
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
        "red_flag" -> Icons.Outlined.WarningAmber
        "overdue" -> Icons.Outlined.CalendarMonth
        else -> Icons.Outlined.Notifications
    }

private fun NotificationItem.displayTitle(): String {
    val bodyLead = body.substringBefore(":").trim()
    return when {
        bodyLead.isLikelyPatientLead() -> bodyLead
        title.isGenericNotificationTitle() && body.isNotBlank() -> body.take(54)
        else -> title
    }
}

private fun NotificationItem.displayBody(titleForRow: String): String {
    val afterLead = if (body.startsWith("$titleForRow:", ignoreCase = true)) {
        body.substringAfter(":").trim()
    } else {
        body.trim()
    }
    val cleaned = afterLead.ifBlank { title }
    return if (type == "red_flag" && cleaned.isNotBlank() && !cleaned.startsWith("Red flag", ignoreCase = true)) {
        "Red flag — $cleaned"
    } else {
        cleaned
    }
}

private fun String.isGenericNotificationTitle(): Boolean =
    equals("Red flag patient", ignoreCase = true) ||
        equals("Task overdue", ignoreCase = true) ||
        equals("New assignment", ignoreCase = true)

private fun String.isLikelyPatientLead(): Boolean =
    length in 3..64 &&
        contains(Regex("[A-Za-z]")) &&
        split(Regex("\\s+")).size <= 5
