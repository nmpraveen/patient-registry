package com.naveenhospital.medtrack.feature.cases

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowForward
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.CloudDone
import androidx.compose.material.icons.outlined.Event
import androidx.compose.material.icons.outlined.HealthAndSafety
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.naveenhospital.medtrack.core.designsystem.MedtrackColors
import com.naveenhospital.medtrack.core.designsystem.MedtrackSectionTitle
import com.naveenhospital.medtrack.core.designsystem.R as DesignR
import com.naveenhospital.medtrack.core.domain.model.CaseCategory
import java.util.Locale

@Composable
@OptIn(ExperimentalLayoutApi::class)
fun CaseCreationScreen(
    pathwayLabel: String,
    category: CaseCategory,
    onBack: () -> Unit,
    onDraftSaved: (String) -> Unit,
    onCreated: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    var step by rememberSaveable { mutableStateOf(0) }
    var fullName by rememberSaveable { mutableStateOf("Keerthana Manikandan") }
    var phone by rememberSaveable { mutableStateOf("+91 98xxx 41200") }
    var age by rememberSaveable { mutableStateOf("27") }
    var sex by rememberSaveable { mutableStateOf("Female") }
    var district by rememberSaveable { mutableStateOf("Coimbatore") }
    var clinicalSummary by rememberSaveable { mutableStateOf(defaultClinicalSummary(category)) }
    var scheduleStart by rememberSaveable { mutableStateOf("Today") }
    var cadence by rememberSaveable { mutableStateOf("Weekly follow-up") }
    var selectedFlags by rememberSaveable {
        mutableStateOf(setOf("Advanced maternal age", "Anaemia"))
    }
    val uhid = "auto \u00B7 ${district.toDistrictPrefix()}-26\u2026"
    val pathwayColor = category.handoffColor()
    val canContinue = fullName.isNotBlank() && phone.isNotBlank() && age.toIntOrNull() != null
    val steps = listOf("Patient", "Clinical", "Schedule")

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(MedtrackColors.Surface)
            .imePadding()
            .navigationBarsPadding(),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(start = 14.dp, end = 14.dp, top = 8.dp, bottom = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconSquareButton(onClick = onBack) {
                Icon(imageVector = Icons.Outlined.Close, contentDescription = "Close", tint = MedtrackColors.Ink)
            }
            Text(
                text = "New case",
                modifier = Modifier.weight(1f),
                color = MedtrackColors.Ink,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.ExtraBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            CategoryChip(label = pathwayLabel, category = category, color = pathwayColor)
        }

        Stepper(steps = steps, currentStep = step)

        LazyColumn(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth(),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                when (step) {
                    0 -> PatientStep(
                        fullName = fullName,
                        onFullNameChange = { fullName = it },
                        phone = phone,
                        onPhoneChange = { phone = it },
                        age = age,
                        onAgeChange = { age = it.filter(Char::isDigit).take(3) },
                        sex = sex,
                        onSexChange = { sex = it },
                        district = district,
                        onDistrictChange = { district = it },
                        uhid = uhid,
                        selectedFlags = selectedFlags,
                        onToggleFlag = { flag ->
                            selectedFlags = if (flag in selectedFlags) selectedFlags - flag else selectedFlags + flag
                        },
                    )
                    1 -> ClinicalStep(
                        category = category,
                        pathwayLabel = pathwayLabel,
                        clinicalSummary = clinicalSummary,
                        onClinicalSummaryChange = { clinicalSummary = it },
                        selectedFlags = selectedFlags,
                        onToggleFlag = { flag ->
                            selectedFlags = if (flag in selectedFlags) selectedFlags - flag else selectedFlags + flag
                        },
                    )
                    else -> ScheduleStep(
                        scheduleStart = scheduleStart,
                        onScheduleStartChange = { scheduleStart = it },
                        cadence = cadence,
                        onCadenceChange = { cadence = it },
                        patientName = fullName.ifBlank { "New patient" },
                        pathwayLabel = pathwayLabel,
                        selectedFlags = selectedFlags,
                    )
                }
            }
        }

        Surface(
            modifier = Modifier.fillMaxWidth(),
            color = MedtrackColors.Card,
            border = BorderStroke(1.dp, MedtrackColors.Border.copy(alpha = 0.72f)),
        ) {
            Row(
                modifier = Modifier.padding(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Button(
                    onClick = { onDraftSaved(fullName.ifBlank { "Draft case" }) },
                    modifier = Modifier.height(52.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MedtrackColors.Card,
                        contentColor = MedtrackColors.InkSoft,
                    ),
                    border = BorderStroke(1.dp, MedtrackColors.Border),
                    contentPadding = PaddingValues(horizontal = 18.dp),
                ) {
                    Text("Save draft", fontWeight = FontWeight.Bold)
                }
                Button(
                    onClick = {
                        if (step < steps.lastIndex) {
                            step += 1
                        } else {
                            onCreated(fullName.ifBlank { "New patient" })
                        }
                    },
                    enabled = canContinue,
                    modifier = Modifier
                        .weight(1f)
                        .height(52.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = MedtrackColors.Primary),
                    contentPadding = PaddingValues(horizontal = 12.dp),
                ) {
                    val label = if (step < steps.lastIndex) "Continue \u00B7 ${steps[step + 1]}" else "Create mock case"
                    Text(label, maxLines = 1, overflow = TextOverflow.Ellipsis, fontWeight = FontWeight.ExtraBold)
                    Spacer(modifier = Modifier.width(7.dp))
                    Icon(
                        imageVector = Icons.AutoMirrored.Outlined.ArrowForward,
                        contentDescription = null,
                        modifier = Modifier.size(19.dp),
                    )
                }
            }
        }
    }
}

@Composable
private fun IconSquareButton(onClick: () -> Unit, content: @Composable () -> Unit) {
    Surface(
        modifier = Modifier.size(42.dp),
        shape = RoundedCornerShape(12.dp),
        color = MedtrackColors.Card,
        border = BorderStroke(1.dp, MedtrackColors.Border),
    ) {
        Box(modifier = Modifier.clickable(onClick = onClick), contentAlignment = Alignment.Center) {
            content()
        }
    }
}

@Composable
private fun Stepper(steps: List<String>, currentStep: Int) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(start = 16.dp, end = 16.dp, bottom = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        steps.forEachIndexed { index, label ->
            val done = index < currentStep
            val current = index == currentStep
            Surface(
                modifier = Modifier.size(24.dp),
                shape = RoundedCornerShape(50),
                color = when {
                    done -> MedtrackColors.Success
                    current -> MedtrackColors.Primary
                    else -> MedtrackColors.SurfaceAlt
                },
            ) {
                Box(contentAlignment = Alignment.Center) {
                    if (done) {
                        Icon(imageVector = Icons.Outlined.Check, contentDescription = null, tint = Color.White, modifier = Modifier.size(15.dp))
                    } else {
                        Text(
                            text = (index + 1).toString(),
                            color = if (current) Color.White else MedtrackColors.Faint,
                            style = MaterialTheme.typography.labelSmall,
                            fontWeight = FontWeight.ExtraBold,
                        )
                    }
                }
            }
            Text(
                text = label,
                color = when {
                    current -> MedtrackColors.Ink
                    done -> MedtrackColors.Success
                    else -> MedtrackColors.Faint
                },
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.ExtraBold,
            )
            if (index < steps.lastIndex) {
                Box(
                    modifier = Modifier
                        .weight(1f)
                        .height(2.dp)
                        .background(
                            color = if (done) MedtrackColors.Success else MedtrackColors.Border,
                            shape = RoundedCornerShape(2.dp),
                        ),
                )
            }
        }
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun PatientStep(
    fullName: String,
    onFullNameChange: (String) -> Unit,
    phone: String,
    onPhoneChange: (String) -> Unit,
    age: String,
    onAgeChange: (String) -> Unit,
    sex: String,
    onSexChange: (String) -> Unit,
    district: String,
    onDistrictChange: (String) -> Unit,
    uhid: String,
    selectedFlags: Set<String>,
    onToggleFlag: (String) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        MedtrackSectionTitle(title = "Patient details")
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            CreateField(label = "Full name", value = fullName, onValueChange = onFullNameChange)
            CreateField(label = "Phone", value = phone, onValueChange = onPhoneChange)
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                CreateField(label = "Age", value = age, onValueChange = onAgeChange, unit = "yrs", modifier = Modifier.weight(0.7f))
                CreateField(label = "Sex", value = sex, onValueChange = onSexChange, modifier = Modifier.weight(1f))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                CreateField(label = "District", value = district, onValueChange = onDistrictChange, modifier = Modifier.weight(1f))
                CreateField(label = "UHID", value = uhid, onValueChange = {}, focused = true, readOnly = true, modifier = Modifier.weight(1f))
            }
        }
        MedtrackSectionTitle(title = "Quick risk flags")
        RiskFlagGrid(selectedFlags = selectedFlags, onToggleFlag = onToggleFlag)
        OfflineNotice()
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun ClinicalStep(
    category: CaseCategory,
    pathwayLabel: String,
    clinicalSummary: String,
    onClinicalSummaryChange: (String) -> Unit,
    selectedFlags: Set<String>,
    onToggleFlag: (String) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        MedtrackSectionTitle(title = "Clinical")
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            CreateReadout(label = "Pathway", value = pathwayLabel, color = category.handoffColor(), modifier = Modifier.weight(1f))
            CreateReadout(label = "Status", value = "Active", color = MedtrackColors.Primary, modifier = Modifier.weight(1f))
        }
        CreateField(
            label = if (category == CaseCategory.ANC) "Primary concern" else "Diagnosis / reason",
            value = clinicalSummary,
            onValueChange = onClinicalSummaryChange,
            minHeight = 82.dp,
        )
        MedtrackSectionTitle(title = "Risk reasons")
        RiskFlagGrid(selectedFlags = selectedFlags, onToggleFlag = onToggleFlag)
        OfflineNotice()
    }
}

@Composable
private fun ScheduleStep(
    scheduleStart: String,
    onScheduleStartChange: (String) -> Unit,
    cadence: String,
    onCadenceChange: (String) -> Unit,
    patientName: String,
    pathwayLabel: String,
    selectedFlags: Set<String>,
) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        MedtrackSectionTitle(title = "Schedule")
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            CreateField(label = "Start", value = scheduleStart, onValueChange = onScheduleStartChange, modifier = Modifier.weight(1f))
            CreateField(label = "Cadence", value = cadence, onValueChange = onCadenceChange, modifier = Modifier.weight(1f))
        }
        Surface(
            shape = RoundedCornerShape(16.dp),
            color = MedtrackColors.Card,
            border = BorderStroke(1.dp, MedtrackColors.Border),
        ) {
            Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(9.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(imageVector = Icons.Outlined.Event, contentDescription = null, tint = MedtrackColors.Primary, modifier = Modifier.size(21.dp))
                    Text("Mock case summary", color = MedtrackColors.Ink, fontWeight = FontWeight.ExtraBold)
                }
                Text(patientName, color = MedtrackColors.Ink, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.ExtraBold)
                Text("$pathwayLabel follow-up starts $scheduleStart.", color = MedtrackColors.Muted, style = MaterialTheme.typography.bodyMedium)
                if (selectedFlags.isNotEmpty()) {
                    Text("${selectedFlags.size} risk reason(s) will seed the case.", color = MedtrackColors.Danger, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.Bold)
                }
            }
        }
        OfflineNotice()
    }
}

@Composable
private fun CreateField(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    unit: String? = null,
    focused: Boolean = false,
    readOnly: Boolean = false,
    minHeight: androidx.compose.ui.unit.Dp = 58.dp,
) {
    val borderColor = if (focused) MedtrackColors.Primary else MedtrackColors.Border
    Surface(
        modifier = modifier.height(minHeight),
        shape = RoundedCornerShape(13.dp),
        color = MedtrackColors.Card,
        border = BorderStroke(1.5.dp, borderColor),
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 13.dp, vertical = 9.dp),
            verticalArrangement = Arrangement.spacedBy(3.dp),
        ) {
            Text(
                text = label,
                color = if (focused) MedtrackColors.Primary else MedtrackColors.Faint,
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.ExtraBold,
            )
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                BasicTextField(
                    value = value,
                    onValueChange = if (readOnly) ({}) else onValueChange,
                    readOnly = readOnly,
                    singleLine = minHeight <= 58.dp,
                    textStyle = MaterialTheme.typography.bodyMedium.copy(
                        color = if (value.isBlank()) MedtrackColors.Faint else MedtrackColors.Ink,
                        fontWeight = FontWeight.Bold,
                    ),
                    modifier = Modifier.weight(1f),
                )
                unit?.let {
                    Text(it, color = MedtrackColors.Faint, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.SemiBold)
                }
            }
        }
    }
}

@Composable
private fun CreateReadout(label: String, value: String, color: Color, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier.height(58.dp),
        shape = RoundedCornerShape(13.dp),
        color = color.copy(alpha = 0.1f),
        border = BorderStroke(1.dp, color.copy(alpha = 0.26f)),
    ) {
        Column(modifier = Modifier.padding(horizontal = 13.dp, vertical = 9.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(label, color = MedtrackColors.Faint, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.ExtraBold)
            Text(value, color = color, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.ExtraBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun RiskFlagGrid(selectedFlags: Set<String>, onToggleFlag: (String) -> Unit) {
    val flags = listOf("Advanced maternal age", "Anaemia", "Prev. C-section", "Hypertension", "Diabetes")
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        flags.forEach { flag ->
            val selected = flag in selectedFlags
            Surface(
                modifier = Modifier.clickable { onToggleFlag(flag) },
                shape = RoundedCornerShape(50),
                color = if (selected) MedtrackColors.Anc else MedtrackColors.Card,
                border = BorderStroke(1.dp, if (selected) MedtrackColors.Anc else MedtrackColors.Border),
            ) {
                Row(
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 7.dp),
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    if (selected) {
                        Icon(imageVector = Icons.Outlined.Check, contentDescription = null, tint = Color.White, modifier = Modifier.size(15.dp))
                    }
                    Text(
                        text = flag,
                        color = if (selected) Color.White else MedtrackColors.InkSoft,
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }
        }
    }
}

@Composable
private fun OfflineNotice() {
    Surface(
        shape = RoundedCornerShape(13.dp),
        color = MedtrackColors.PrimarySoft,
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 13.dp, vertical = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(9.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(imageVector = Icons.Outlined.CloudDone, contentDescription = null, tint = MedtrackColors.Primary, modifier = Modifier.size(20.dp))
            Text(
                text = "Saved on-device now, synced when online. No more web detour.",
                color = MedtrackColors.PrimaryDark,
                style = MaterialTheme.typography.bodySmall,
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}

@Composable
private fun CategoryChip(label: String, category: CaseCategory, color: Color) {
    Surface(
        shape = RoundedCornerShape(50),
        color = color.copy(alpha = 0.12f),
        border = BorderStroke(1.dp, color.copy(alpha = 0.24f)),
    ) {
        Row(
            modifier = Modifier.padding(start = 8.dp, end = 11.dp, top = 4.dp, bottom = 4.dp),
            horizontalArrangement = Arrangement.spacedBy(5.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                painter = painterResource(category.creationIconResId()),
                contentDescription = null,
                tint = color,
                modifier = Modifier.size(16.dp),
            )
            Text(label, color = color, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold)
        }
    }
}

private fun CaseCategory.creationIconResId(): Int =
    when (this) {
        CaseCategory.ANC -> DesignR.drawable.ic_cat_anc
        CaseCategory.SURGERY -> DesignR.drawable.ic_cat_surgery
        else -> DesignR.drawable.ic_cat_medicine
    }

private fun CaseCategory.handoffColor(): Color =
    when (this) {
        CaseCategory.ANC -> MedtrackColors.Anc
        CaseCategory.SURGERY -> MedtrackColors.Surgery
        CaseCategory.MEDICINE -> MedtrackColors.Medicine
        else -> MedtrackColors.Primary
    }

private fun String.toDistrictPrefix(): String {
    val district = trim().lowercase(Locale.US)
    val suffix = when {
        "coimbatore" in district -> "CBE"
        "salem" in district -> "SLM"
        "thanjavur" in district -> "TNJ"
        "madurai" in district -> "MDU"
        district.length >= 3 -> district.take(3).uppercase(Locale.US)
        else -> "CBE"
    }
    return "TN-$suffix"
}

private fun defaultClinicalSummary(category: CaseCategory): String =
    when (category) {
        CaseCategory.ANC -> "First trimester ANC follow-up"
        CaseCategory.SURGERY -> "Pre-operative fitness review"
        CaseCategory.MEDICINE -> "Diabetes follow-up"
        CaseCategory.OTHER -> "Custom follow-up"
    }
