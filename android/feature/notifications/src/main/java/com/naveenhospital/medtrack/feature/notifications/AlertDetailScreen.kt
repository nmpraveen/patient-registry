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
    val title = notification?.alertHeadline(patientCase) ?: "Alert unavailable"
    val body = notification?.alertSummary(patientCase, title) ?: "This alert could not be found in the local inbox cache."
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
private fun PatientContextCard(patientCase: PatientCase?) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        MedtrackSectionEyebrow(title = "Patient")
        if (patientCase == null) {
            MedtrackCompactCard {
            Text("Case context is not cached on this device yet.", color = MedtrackColors.Muted)
            }
        } else {
            val visual = medtrackCategoryVisual(patientCase.category.name, patientCase.categoryLabel)
            MedtrackCompactCard {
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
private fun BreachedThresholdsCard(notification: NotificationItem?, patientCase: PatientCase?) {
    val color = notification?.alertColor() ?: MedtrackColors.Muted
    val metricRows = patientCase?.latestVitalSummary.toAlertMetricRows()
    val rows = breachRows(notification = notification, patientCase = patientCase)
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        val count = metricRows.size.takeIf { it > 0 } ?: rows.size.takeIf { it > 0 }
        MedtrackSectionEyebrow(title = "Why this fired", trailing = count?.toString())
        MedtrackCompactCard {
            if (metricRows.isNotEmpty()) {
                metricRows.forEach { row ->
                    AlertMetricRow(row = row)
                }
            } else {
                if (rows.isEmpty()) {
                    Text(
                        text = "This notification does not include structured fired-reason details on this device.",
                        color = MedtrackColors.Muted,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                rows.forEach { row ->
                    AlertReasonRow(text = row, color = color)
                }
            }
        }
    }
}

@Composable
private fun AlertMetricRow(row: AlertMetricDisplay) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 4.dp, vertical = 7.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = row.label,
            color = MedtrackColors.Ink,
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.ExtraBold,
            modifier = Modifier.width(38.dp),
        )
        Text(
            text = row.value,
            color = row.color,
            style = MaterialTheme.typography.bodySmall,
            fontWeight = FontWeight.ExtraBold,
            modifier = Modifier.weight(1f),
        )
        Text(
            text = row.threshold,
            color = MedtrackColors.Faint,
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
        )
        Text(
            text = row.symbol,
            color = row.color,
            style = MaterialTheme.typography.bodySmall,
            fontWeight = FontWeight.ExtraBold,
        )
    }
}

@Composable
private fun AlertReasonRow(text: String, color: Color) {
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
            Text(text, color = MedtrackColors.Ink, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
            Text("active", color = color, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold)
        }
    }
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

private fun breachRows(notification: NotificationItem?, patientCase: PatientCase?): List<String> {
    val riskRows = patientCase?.highRiskReasons.orEmpty().filter { it.isNotBlank() }
    if (riskRows.isNotEmpty()) return riskRows.take(3)
    val body = notification?.body?.takeIf { it.isNotBlank() }
    val latestVitals = patientCase?.latestVitalSummary?.takeIf { it.isNotBlank() }
    return listOfNotNull(
        body,
        latestVitals?.let { "Latest vitals: $it" },
    ).take(3)
}

private fun NotificationItem.alertHeadline(patientCase: PatientCase?): String {
    val displayTitle = displayTitle()
    val bodyText = displayBody(displayTitle)
    val metric = patientCase?.latestVitalSummary.toAlertMetricRows().firstOrNull { it.alerting }
    return when {
        metric?.plainHeadline != null -> metric.plainHeadline
        bodyText.plainRiskHeadline() != null -> bodyText.plainRiskHeadline()!!
        bodyText.isNotBlank() && !bodyText.isLikelyPatientLead() -> bodyText.take(54)
        !title.isGenericNotificationTitle() -> title
        patientCase?.highRiskReasons?.firstOrNull { it.isNotBlank() } != null -> patientCase.highRiskReasons.first { it.isNotBlank() }
        else -> typeLabel()
    }
}

private fun NotificationItem.alertSummary(patientCase: PatientCase?, headline: String): String {
    val timestamp = createdAt.takeIf { it.isNotBlank() }?.let { medtrackTimestampLabel(it) ?: it }
    val metric = patientCase?.latestVitalSummary.toAlertMetricRows().firstOrNull { it.alerting }
    return when {
        metric != null -> {
            listOfNotNull(
                "${metric.value} logged${timestamp?.let { " $it" }.orEmpty()} ${metric.summaryVerb} ${metric.threshold.lowercase()} threshold.",
                patientCase?.diagnosis?.takeIf { it.isNotBlank() }?.let { "Context: $it." },
            ).joinToString(" ")
        }
        type == "red_flag" && patientCase != null -> {
            val context = patientCase.diagnosis.takeIf { it.isNotBlank() } ?: patientCase.categoryLabel
            val opening = if (headline.endsWith(" active", ignoreCase = true)) {
                "$headline for this case."
            } else {
                "$headline is active for this case."
            }
            listOfNotNull(
                opening,
                context.takeIf { it.isNotBlank() }?.let { "Context: $it." },
                timestamp?.let { "Logged $it." },
            ).joinToString(" ")
        }
        timestamp != null -> "$headline logged $timestamp."
        else -> displayBody(displayTitle()).ifBlank { title }
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
    type == "red_flag"

private fun NotificationItem.alertColor(): Color =
    when (type) {
        "red_flag" -> MedtrackColors.Danger
        "overdue" -> MedtrackColors.Warning
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
    return afterLead.ifBlank { title }
}

private fun String.isGenericNotificationTitle(): Boolean =
    equals("Red flag patient", ignoreCase = true) ||
        equals("Task overdue", ignoreCase = true) ||
        equals("New assignment", ignoreCase = true)

private fun String.isLikelyPatientLead(): Boolean =
    length in 3..64 &&
        contains(Regex("[A-Za-z]")) &&
        split(Regex("\\s+")).size <= 5

private fun String.plainRiskHeadline(): String? {
    val normalized = trim().lowercase()
    return when {
        normalized == "shtn" || normalized.contains("hypertension") || normalized.contains("pih") -> "Blood pressure high"
        normalized.contains("anemia") -> "Hemoglobin low"
        normalized.contains("thyroid") -> "Thyroid risk active"
        normalized.contains("smoking") -> "Smoking risk active"
        normalized == "high risk" -> "High-risk case"
        else -> null
    }
}

private data class AlertMetricDisplay(
    val label: String,
    val value: String,
    val threshold: String,
    val alerting: Boolean,
    val plainHeadline: String?,
    val summaryVerb: String,
) {
    val color: Color = if (alerting) MedtrackColors.Danger else MedtrackColors.Success
    val symbol: String = if (alerting) "↑" else "✓"
}

private fun String?.toAlertMetricRows(): List<AlertMetricDisplay> {
    val summary = this?.takeIf { it.isNotBlank() } ?: return emptyList()
    val rows = mutableListOf<AlertMetricDisplay>()
    Regex("""BP\s+(\d{2,3})/(\d{2,3})""", RegexOption.IGNORE_CASE).find(summary)?.let { match ->
        val systolic = match.groupValues[1].toIntOrNull()
        val diastolic = match.groupValues[2].toIntOrNull()
        systolic?.let {
            rows += AlertMetricDisplay(
                label = "SBP",
                value = "$it mmHg",
                threshold = "thresh ≥140",
                alerting = it >= 140,
                plainHeadline = if (it >= 140) "Blood pressure high" else null,
                summaryVerb = if (it >= 140) "exceeds" else "is within",
            )
        }
        diastolic?.let {
            rows += AlertMetricDisplay(
                label = "DBP",
                value = "$it mmHg",
                threshold = "thresh ≥90",
                alerting = it >= 90,
                plainHeadline = if (it >= 90) "Blood pressure high" else null,
                summaryVerb = if (it >= 90) "exceeds" else "is within",
            )
        }
    }
    Regex("""(?:PR|Pulse)\s+(\d{2,3})""", RegexOption.IGNORE_CASE).find(summary)?.groupValues?.getOrNull(1)?.toIntOrNull()?.let {
        rows += AlertMetricDisplay(
            label = "PR",
            value = "$it bpm",
            threshold = "range 60-100",
            alerting = it < 60 || it > 100,
            plainHeadline = if (it < 60 || it > 100) "Pulse out of range" else null,
            summaryVerb = if (it < 60 || it > 100) "is outside" else "is within",
        )
    }
    Regex("""SpO2\s+(\d{2,3})""", RegexOption.IGNORE_CASE).find(summary)?.groupValues?.getOrNull(1)?.toIntOrNull()?.let {
        rows += AlertMetricDisplay(
            label = "SpO2",
            value = "$it%",
            threshold = "thresh ≥95",
            alerting = it < 95,
            plainHeadline = if (it < 95) "Oxygen saturation low" else null,
            summaryVerb = if (it < 95) "is below" else "meets",
        )
    }
    Regex("""Hb\s+(\d+(?:\.\d+)?)""", RegexOption.IGNORE_CASE).find(summary)?.groupValues?.getOrNull(1)?.toDoubleOrNull()?.let {
        rows += AlertMetricDisplay(
            label = "Hb",
            value = "${it.trimMetric()} g/dL",
            threshold = "thresh ≥11",
            alerting = it < 11.0,
            plainHeadline = if (it < 11.0) "Hemoglobin low" else null,
            summaryVerb = if (it < 11.0) "is below" else "meets",
        )
    }
    return rows.take(4)
}

private fun Double.trimMetric(): String =
    if (this % 1.0 == 0.0) toInt().toString() else toString()
