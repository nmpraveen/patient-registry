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
import androidx.compose.material.icons.outlined.Phone
import androidx.compose.material.icons.outlined.WarningAmber
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
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
import com.naveenhospital.medtrack.core.designsystem.MedtrackMiniPill
import com.naveenhospital.medtrack.core.designsystem.MedtrackSectionTitle
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
            IconButton(onClick = onBack) {
                Icon(imageVector = Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "Back")
            }
            Text(
                text = "Alert detail",
                color = MedtrackColors.Ink,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.ExtraBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
            MedtrackMiniPill(
                text = notification?.typeLabel() ?: "Missing",
                color = notification?.alertColor() ?: MedtrackColors.Muted,
            )
        }

        Column(
            modifier = Modifier
                .weight(1f)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            AlertHero(notification = notification)
            PatientContextCard(patientCase = patientCase)
            BreachedThresholdsCard(notification = notification, patientCase = patientCase)
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
                    Text("Call", maxLines = 1, overflow = TextOverflow.Ellipsis)
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
private fun AlertHero(notification: NotificationItem?) {
    val color = notification?.alertColor() ?: MedtrackColors.Muted
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(22.dp),
        color = if (notification?.isCritical() == true) MedtrackColors.DangerSoft else MedtrackColors.Card,
        border = BorderStroke(1.dp, color.copy(alpha = 0.24f)),
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.Top,
        ) {
            Surface(shape = RoundedCornerShape(15.dp), color = color.copy(alpha = 0.12f), modifier = Modifier.size(48.dp)) {
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
                    text = notification?.title ?: "Alert unavailable",
                    color = if (notification?.isCritical() == true) MedtrackColors.Danger else MedtrackColors.Ink,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.ExtraBold,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = notification?.body ?: "This alert could not be found in the local inbox cache.",
                    color = MedtrackColors.InkSoft,
                    style = MaterialTheme.typography.bodyMedium,
                    maxLines = 4,
                    overflow = TextOverflow.Ellipsis,
                )
                notification?.createdAt?.takeIf { it.isNotBlank() }?.let {
                    Text(it.take(16), color = MedtrackColors.Muted, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.SemiBold)
                }
            }
        }
    }
}

@Composable
private fun PatientContextCard(patientCase: PatientCase?) {
    MedtrackCompactCard {
        MedtrackSectionTitle(title = "Patient context")
        if (patientCase == null) {
            Text("Case context is not cached on this device yet.", color = MedtrackColors.Muted)
        } else {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text(patientCase.patientName, color = MedtrackColors.Ink, fontWeight = FontWeight.ExtraBold, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    Text(patientCase.identityLine(), color = MedtrackColors.Muted, style = MaterialTheme.typography.labelMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
                MedtrackMiniPill(text = patientCase.categoryLabel, color = patientCase.alertCategoryColor())
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

@Composable
private fun BreachedThresholdsCard(notification: NotificationItem?, patientCase: PatientCase?) {
    val color = notification?.alertColor() ?: MedtrackColors.Muted
    val rows = breachRows(notification = notification, patientCase = patientCase)
    MedtrackCompactCard {
        MedtrackSectionTitle(title = "What fired", trailing = "${rows.size}")
        rows.forEach { row ->
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(13.dp),
                color = color.copy(alpha = 0.08f),
                border = BorderStroke(1.dp, color.copy(alpha = 0.18f)),
            ) {
                Row(
                    modifier = Modifier.padding(horizontal = 10.dp, vertical = 9.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Box(
                        modifier = Modifier
                            .size(8.dp)
                            .background(color, RoundedCornerShape(50)),
                    )
                    Text(row, color = MedtrackColors.Ink, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                }
            }
        }
    }
}

private fun breachRows(notification: NotificationItem?, patientCase: PatientCase?): List<String> {
    val riskRows = patientCase?.highRiskReasons.orEmpty().filter { it.isNotBlank() }
    if (riskRows.isNotEmpty()) return riskRows.take(3)
    val body = notification?.body?.takeIf { it.isNotBlank() }
    val latestVitals = patientCase?.latestVitalSummary?.takeIf { it.isNotBlank() }
    return listOfNotNull(
        body,
        latestVitals?.let { "Latest vitals: $it" },
    ).ifEmpty {
        listOf("Mock critical threshold breach for review")
    }.take(3)
}

private fun PatientCase.identityLine(): String =
    listOfNotNull(uhid, age?.let { "${it}y" }, sexLabel, place)
        .filter { it.isNotBlank() }
        .joinToString(" - ")

private fun PatientCase.alertCategoryColor(): Color =
    if (categoryLabel.contains("rehab", ignoreCase = true)) {
        MedtrackColors.CustomRehab
    } else {
        when (category.name) {
            "ANC" -> MedtrackColors.Anc
            "SURGERY" -> MedtrackColors.Surgery
            "MEDICINE" -> MedtrackColors.Medicine
            else -> MedtrackColors.Primary
        }
    }

private fun NotificationItem.isCritical(): Boolean =
    type in setOf("red_flag", "overdue")

private fun NotificationItem.alertColor(): Color =
    when (type) {
        "red_flag" -> MedtrackColors.Danger
        "overdue" -> MedtrackColors.Danger
        "assignment" -> MedtrackColors.Primary
        else -> MedtrackColors.Muted
    }

private fun NotificationItem.typeLabel(): String =
    when (type) {
        "red_flag" -> "Red flag"
        "overdue" -> "Overdue"
        "assignment" -> "Assigned"
        else -> "Info"
    }
