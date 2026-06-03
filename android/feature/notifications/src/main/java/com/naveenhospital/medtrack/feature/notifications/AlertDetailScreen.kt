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
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.OpenInNew
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material.icons.outlined.KeyboardArrowRight
import androidx.compose.material.icons.outlined.Phone
import androidx.compose.material.icons.outlined.WarningAmber
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
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
import com.naveenhospital.medtrack.core.designsystem.MedtrackCategoryTile
import com.naveenhospital.medtrack.core.designsystem.MedtrackColors
import com.naveenhospital.medtrack.core.designsystem.MedtrackCompactCard
import com.naveenhospital.medtrack.core.designsystem.MedtrackSectionEyebrow
import com.naveenhospital.medtrack.core.designsystem.medtrackCategoryVisual
import com.naveenhospital.medtrack.core.designsystem.medtrackTimestampLabel
import com.naveenhospital.medtrack.core.domain.model.NotificationItem
import com.naveenhospital.medtrack.core.domain.model.PatientCase

@Composable
fun AlertDetailScreen(
    notification: NotificationItem?,
    patientCase: PatientCase?,
    onBack: () -> Unit,
    onCallPatient: (PatientCase) -> Unit,
    onOpenCase: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val openCaseId = patientCase?.id ?: notification?.caseId

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(MedtrackColors.Surface)
            .navigationBarsPadding()
            .padding(horizontal = 10.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            AlertHeaderIconButton(onClick = onBack)
            Text(
                text = "Alert",
                color = MedtrackColors.Ink,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.ExtraBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
            Text(
                text = notification?.createdAt?.shortAlertTimeLabel() ?: "now",
                color = MedtrackColors.Faint,
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.Bold,
            )
        }

        Column(
            modifier = Modifier
                .weight(1f)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
                AlertHero(notification = notification, patientCase = patientCase)
            PatientContextCard(
                patientCase = patientCase,
                onOpenCase = { openCaseId?.let(onOpenCase) },
            )
            WhyThisFiredCard(notification = notification)
        }

        Surface(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(22.dp),
            color = MedtrackColors.Card,
            border = BorderStroke(1.dp, MedtrackColors.Border),
            shadowElevation = 10.dp,
        ) {
            Row(
                modifier = Modifier.padding(8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Button(
                    onClick = { patientCase?.let(onCallPatient) },
                    enabled = !patientCase?.phoneNumber.isNullOrBlank(),
                    modifier = Modifier
                        .weight(1f)
                        .height(46.dp),
                    contentPadding = PaddingValues(horizontal = 8.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = MedtrackColors.Success),
                ) {
                    Icon(imageVector = Icons.Outlined.Phone, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(5.dp))
                    Text("Call now", maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                Button(
                    onClick = { openCaseId?.let(onOpenCase) },
                    enabled = openCaseId != null,
                    modifier = Modifier
                        .weight(1f)
                        .height(46.dp),
                    contentPadding = PaddingValues(horizontal = 8.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = MedtrackColors.Ink),
                ) {
                    Icon(imageVector = Icons.AutoMirrored.Outlined.OpenInNew, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(5.dp))
                    Text("Open case", maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
            }
        }
    }
}

@Composable
private fun AlertHero(notification: NotificationItem?, patientCase: PatientCase?) {
    val color = notification?.alertColor() ?: MedtrackColors.Muted
    val title = notification?.alertHeadline() ?: "Alert unavailable"
    val body = notification?.alertSummary() ?: "This alert could not be found in the local inbox cache."
    val eyebrow = listOfNotNull(
        notification?.typeLabel()?.uppercase(),
        patientCase?.categoryLabel?.uppercase()?.takeIf { it.isNotBlank() },
    ).joinToString(" · ").ifBlank { "ALERT" }
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        color = if (notification?.isCritical() == true) MedtrackColors.DangerSoft else MedtrackColors.Card,
        border = BorderStroke(1.dp, color.copy(alpha = 0.24f)),
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.Top,
        ) {
            Surface(shape = RoundedCornerShape(12.dp), color = color.copy(alpha = 0.10f), modifier = Modifier.size(40.dp)) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(
                        imageVector = if (notification?.isCritical() == true) Icons.Outlined.WarningAmber else Icons.Outlined.ErrorOutline,
                        contentDescription = null,
                        tint = color,
                        modifier = Modifier.size(27.dp),
                    )
                }
            }
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                Text(
                    text = eyebrow,
                    color = color,
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.ExtraBold,
                    maxLines = 1,
                )
                Text(
                    text = title,
                    color = if (notification?.isCritical() == true) MedtrackColors.Danger else MedtrackColors.Ink,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.ExtraBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = body,
                    color = MedtrackColors.InkSoft,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 3,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

@Composable
private fun PatientContextCard(
    patientCase: PatientCase?,
    onOpenCase: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        MedtrackSectionEyebrow(title = "Patient")
        if (patientCase == null) {
            MedtrackCompactCard {
            Text("Case context is not cached on this device yet.", color = MedtrackColors.Muted)
            }
        } else {
            val visual = medtrackCategoryVisual(patientCase.category.name, patientCase.categoryLabel)
            MedtrackCompactCard(modifier = Modifier.clickable(onClick = onOpenCase)) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                MedtrackCategoryTile(
                    iconResId = visual.iconResId,
                    tint = visual.tint,
                    softColor = visual.soft,
                    size = 42.dp,
                )
                Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text(patientCase.patientName, color = MedtrackColors.Ink, fontWeight = FontWeight.ExtraBold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    Text(patientCase.identityLine(), color = MedtrackColors.Muted, style = MaterialTheme.typography.labelMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
                Icon(imageVector = Icons.Outlined.KeyboardArrowRight, contentDescription = null, tint = MedtrackColors.Faint, modifier = Modifier.size(18.dp))
            }
            Text(
                text = patientCase.diagnosis.ifBlank { "No diagnosis summary" },
                color = MedtrackColors.InkSoft,
                style = MaterialTheme.typography.bodySmall,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            }
        }
    }
}

@Composable
private fun WhyThisFiredCard(notification: NotificationItem?) {
    val rows = notification?.whyThisFiredRows().orEmpty()
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        val count = rows.size.takeIf { it > 0 }
        MedtrackSectionEyebrow(title = "Why this fired", trailing = count?.toString())
        MedtrackCompactCard {
            if (rows.isEmpty()) {
                Text(
                    text = "This notification does not include structured fired-reason details on this device.",
                    color = MedtrackColors.Muted,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            rows.forEach { row ->
                AlertReasonRow(row = row)
            }
        }
    }
}

@Composable
private fun AlertReasonRow(row: WhyThisFiredRow) {
    val color = row.tone.reasonColor()
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        color = MedtrackColors.Card,
        border = BorderStroke(1.dp, MedtrackColors.Border),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 9.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(
                modifier = Modifier
                    .size(7.dp)
                    .background(color, RoundedCornerShape(50)),
            )
            Text(
                row.label,
                color = MedtrackColors.Faint,
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.ExtraBold,
                maxLines = 1,
            )
            Text(
                row.value,
                color = MedtrackColors.Ink,
                style = MaterialTheme.typography.bodySmall,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.weight(1f),
            )
        }
    }
}

@Composable
private fun AlertReasonTone.reasonColor(): Color =
    when (this) {
        AlertReasonTone.Danger -> MedtrackColors.Danger
        AlertReasonTone.Warning -> MedtrackColors.Warning
        AlertReasonTone.Primary -> MedtrackColors.Primary
        AlertReasonTone.Success -> MedtrackColors.Success
        AlertReasonTone.Muted -> MedtrackColors.Muted
    }

@Composable
private fun AlertHeaderIconButton(onClick: () -> Unit) {
    Surface(
        modifier = Modifier
            .size(42.dp)
            .clickable(onClick = onClick),
        shape = RoundedCornerShape(12.dp),
        color = Color.White,
        border = BorderStroke(1.dp, MedtrackColors.Border),
        tonalElevation = 0.dp,
    ) {
        Box(contentAlignment = Alignment.Center) {
            Icon(imageVector = Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "Back", tint = MedtrackColors.Ink, modifier = Modifier.size(20.dp))
        }
    }
}

private fun String.shortAlertTimeLabel(): String {
    val label = medtrackTimestampLabel(this) ?: return "now"
    return when {
        label.startsWith("Today", ignoreCase = true) -> "now"
        label.contains(" ") -> label.substringBeforeLast(" ")
        else -> label
    }
}

private fun PatientCase.identityLine(): String =
    listOfNotNull(uhid, age?.let { "${it}y" }, sexLabel, place)
        .filter { it.isNotBlank() }
        .joinToString(" - ")

private fun PatientCase.alertCategoryColor(): Color =
    when (category.name) {
        "ANC" -> MedtrackColors.Anc
        "SURGERY" -> MedtrackColors.Surgery
        "MEDICINE" -> MedtrackColors.Medicine
        else -> MedtrackColors.Primary
    }

private fun NotificationItem.isCritical(): Boolean =
    normalizedType() == "red_flag"

private fun NotificationItem.alertColor(): Color =
    when (normalizedType()) {
        "red_flag" -> MedtrackColors.Danger
        "overdue" -> MedtrackColors.Warning
        "assignment" -> MedtrackColors.Primary
        else -> MedtrackColors.Muted
    }

private fun NotificationItem.typeLabel(): String =
    when (normalizedType()) {
        "red_flag" -> "Red flag"
        "overdue" -> "Overdue"
        "assignment" -> "Assigned"
        else -> "Info"
    }
