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
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.ArrowForward
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.naveenhospital.medtrack.core.designsystem.MedtrackColors
import com.naveenhospital.medtrack.core.designsystem.MedtrackSectionTitle
import com.naveenhospital.medtrack.core.domain.model.CaseCategory
import com.naveenhospital.medtrack.core.domain.model.CaseCreateOutcome
import com.naveenhospital.medtrack.core.domain.model.CaseFormMetadata
import com.naveenhospital.medtrack.core.domain.model.FormChoice
import com.naveenhospital.medtrack.core.domain.model.NewCaseInput
import com.naveenhospital.medtrack.core.domain.model.PatientLookup
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone

private val FieldHeight = 64.dp

private fun String.isAnc() = trim().equals("ANC", ignoreCase = true)
private fun String.isSurgery() = trim().equals("Surgery", ignoreCase = true)

@Composable
fun CaseCreationScreen(
    initialCategory: CaseCategory,
    pathwayLabel: String,
    loadMetadata: suspend () -> CaseFormMetadata,
    searchPatients: suspend (String) -> List<PatientLookup>,
    submit: suspend (NewCaseInput) -> CaseCreateOutcome,
    onBack: () -> Unit,
    onCreated: (Long, String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val scope = rememberCoroutineScope()
    var metadata by remember { mutableStateOf<CaseFormMetadata?>(null) }
    var loadError by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        runCatching { loadMetadata() }
            .onSuccess { metadata = it }
            .onFailure { loadError = it.message ?: "Unable to load form" }
    }

    val meta = metadata
    when {
        loadError != null -> CenterState("Couldn't load the form", loadError, onBack)
        meta == null -> CenterState("Loading form…", null, onBack, loading = true)
        !meta.canCreate -> CenterState(
            "No permission",
            "Your role can't create cases. Ask an administrator for access.",
            onBack,
        )
        else -> CaseCreationForm(
            metadata = meta,
            initialCategory = initialCategory,
            pathwayLabel = pathwayLabel,
            searchPatients = searchPatients,
            onBack = onBack,
            onSubmit = { input, onResult ->
                scope.launch {
                    val outcome = runCatching { submit(input) }.getOrElse {
                        CaseCreateOutcome.Failure(it.message ?: "Network error. Try again.")
                    }
                    onResult(outcome)
                }
            },
            onCreated = onCreated,
            modifier = modifier,
        )
    }
}

@Composable
private fun CaseCreationForm(
    metadata: CaseFormMetadata,
    initialCategory: CaseCategory,
    pathwayLabel: String,
    searchPatients: suspend (String) -> List<PatientLookup>,
    onBack: () -> Unit,
    onSubmit: (NewCaseInput, (CaseCreateOutcome) -> Unit) -> Unit,
    onCreated: (Long, String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val state = remember { CaseFormState(metadata, initialCategory) }
    state.searchPatients = searchPatients
    var step by remember { mutableStateOf(0) }
    var submitting by remember { mutableStateOf(false) }
    var banner by remember { mutableStateOf<String?>(null) }

    val category = state.category
    val stepTitles = state.stepTitles()
    val pathwayColor = category?.name.handoffColor()

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(MedtrackColors.Surface)
            .imePadding()
            .navigationBarsPadding(),
    ) {
        // Header
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(start = 14.dp, end = 14.dp, top = 10.dp, bottom = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconSquareButton(onClick = onBack) {
                Icon(Icons.Outlined.Close, contentDescription = "Close", tint = MedtrackColors.Ink)
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
            CategoryChip(category?.name ?: pathwayLabel, pathwayColor)
        }

        Stepper(stepTitles, step)

        LazyColumn(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth(),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                when (stepTitles.getOrNull(step)) {
                    "Patient" -> PatientStep(state)
                    "Clinical" -> ClinicalStep(state, pathwayColor)
                    "ANC", "Surgery", "Medicine" -> PathwayStep(state)
                    else -> ReviewStep(state)
                }
            }
        }

        // Fixed bottom area: banner (always visible) + buttons
        Column(modifier = Modifier.fillMaxWidth()) {
            banner?.let { BannerError(it) }
            BottomBar(
                primaryLabel = if (step < stepTitles.lastIndex) "Continue" else "Create case",
                submitting = submitting,
                showBack = step > 0,
                onBack = { if (step > 0) { banner = null; step -= 1 } },
                onPrimary = {
                    banner = null
                    val stepError = state.validateStep(stepTitles[step])
                    if (stepError != null) {
                        banner = stepError
                        return@BottomBar
                    }
                    if (step < stepTitles.lastIndex) {
                        step += 1
                    } else {
                        submitting = true
                        onSubmit(state.toInput()) { outcome ->
                            submitting = false
                            when (outcome) {
                                is CaseCreateOutcome.Success -> onCreated(outcome.caseId, outcome.message)
                                is CaseCreateOutcome.ValidationError -> banner = outcome.bannerText()
                                is CaseCreateOutcome.Failure -> banner = outcome.message
                            }
                        }
                    }
                },
            )
        }
    }
}

private fun CaseCreateOutcome.ValidationError.bannerText(): String {
    val details = errors.values.flatten().take(3)
    return if (details.isEmpty()) message else details.joinToString("  •  ")
}

/* ----------------------------- Steps ----------------------------- */

@Composable
private fun PatientStep(state: CaseFormState) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        SegmentedToggle(
            options = listOf("New patient" to "new", "Existing patient" to "existing"),
            selected = state.patientMode,
            onSelect = { state.patientMode = it },
        )
        if (state.patientMode == "existing") {
            ExistingPatientPicker(state)
        } else {
            NewPatientFields(state)
        }
    }
}

@Composable
private fun ExistingPatientPicker(state: CaseFormState) {
    val scope = rememberCoroutineScope()
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SearchField(
            value = state.patientQuery,
            onValueChange = {
                state.patientQuery = it
                scope.launch {
                    state.searching = true
                    state.patientResults = runCatching { state.searchPatients(it) }.getOrDefault(emptyList())
                    state.searching = false
                }
            },
        )
        state.selectedPatient?.let { picked ->
            Surface(
                shape = RoundedCornerShape(14.dp),
                color = MedtrackColors.PrimarySoft,
                border = BorderStroke(1.dp, MedtrackColors.Primary.copy(alpha = 0.4f)),
            ) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text(picked.name.ifBlank { "Patient" }, color = MedtrackColors.Ink, fontWeight = FontWeight.ExtraBold)
                    Text(
                        "${picked.uhid}  •  ${picked.genderLabel}  •  ${picked.age ?: "-"}y",
                        color = MedtrackColors.Muted,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
        }
        if (state.searching) {
            Text("Searching…", color = MedtrackColors.Faint, style = MaterialTheme.typography.bodySmall)
        }
        state.patientResults.take(6).forEach { patient ->
            Surface(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { state.selectPatient(patient) },
                shape = RoundedCornerShape(13.dp),
                color = MedtrackColors.Card,
                border = BorderStroke(1.dp, MedtrackColors.Border),
            ) {
                Column(Modifier.padding(13.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(patient.name.ifBlank { "Unnamed" }, color = MedtrackColors.Ink, fontWeight = FontWeight.Bold)
                    Text(
                        "${patient.uhid}  •  ${patient.phoneNumber.ifBlank { "no phone" }}",
                        color = MedtrackColors.Muted,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
        }
    }
}

@Composable
private fun NewPatientFields(state: CaseFormState) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        ToggleRow(
            label = "Use temporary patient ID",
            help = "Generate a local ID now; add the real UHID later.",
            checked = state.useTemporaryUhid,
            onChange = { state.useTemporaryUhid = it },
        )
        if (!state.useTemporaryUhid) {
            TextField("UHID", state.uhid) { state.uhid = it }
        }
        FieldRow {
            DropdownField("Prefix", state.prefix, state.metadata.prefixes, { state.prefix = it }, Modifier.weight(1f))
            TextField("First name", state.firstName, Modifier.weight(1.6f)) { state.firstName = it }
        }
        TextField("Last name", state.lastName) { state.lastName = it }
        FieldRow {
            DropdownField("Sex", state.gender, state.metadata.genders, { state.gender = it }, Modifier.weight(1f))
            TextField("Age", state.age, Modifier.weight(0.8f), keyboard = KeyboardType.Number) {
                state.age = it.filter(Char::isDigit).take(3)
            }
        }
        FieldRow {
            TextField("Phone", state.phone, Modifier.weight(1.3f), keyboard = KeyboardType.Phone) {
                state.phone = it.filter(Char::isDigit).take(10)
            }
            DropdownField("Blood group", state.bloodGroup, state.metadata.bloodGroups, { state.bloodGroup = it }, Modifier.weight(1f), optional = true)
        }
        TextField("Place / district", state.place, optional = true) { state.place = it }
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun ClinicalStep(state: CaseFormState, categoryColor: Color) {
    val category = state.category
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        // Chosen category shown read-only (picked in quick-add)
        ReadonlyField(label = "Category", value = category?.name ?: "-", tint = categoryColor)
        if (category != null && category.subcategories.isNotEmpty()) {
            DropdownField("Subcategory", state.subcategory, category.subcategories, { state.subcategory = it })
        }
        MultilineField("Diagnosis / reason", state.diagnosis) { state.diagnosis = it }
        TextField("Referred by", state.referredBy, optional = true) { state.referredBy = it }
        ToggleRow(
            label = "High risk",
            help = "Flag this case for closer follow-up.",
            checked = state.highRisk,
            onChange = { state.highRisk = it },
        )
        MedtrackSectionTitle(title = "Comorbidities (NCD)")
        MultiSelectChips(state.metadata.ncdFlags, state.ncdFlags, { state.toggleNcd(it) }, MedtrackColors.Medicine)
        MultilineField("Notes", state.notes, optional = true) { state.notes = it }
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun PathwayStep(state: CaseFormState) {
    val category = state.category ?: return
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        when {
            category.name.isAnc() -> {
                MedtrackSectionTitle(title = "Obstetric history (GPLA)")
                FieldRow {
                    GplaField("G", state.gravida, { state.gravida = it }, Modifier.weight(1f))
                    GplaField("P", state.para, { state.para = it }, Modifier.weight(1f))
                    GplaField("A", state.abortions, { state.abortions = it }, Modifier.weight(1f))
                    GplaField("L", state.living, { state.living = it }, Modifier.weight(1f))
                }
                FieldRow {
                    GplaField("FTND", state.ftnd, { state.ftnd = it }, Modifier.weight(1f))
                    GplaField("LSCS", state.lscs, { state.lscs = it }, Modifier.weight(1f))
                    Spacer(Modifier.weight(2f))
                }
                MedtrackSectionTitle(title = "Pregnancy dates")
                DateField("LMP", state.lmp) { state.lmp = it }
                FieldRow {
                    DateField("EDD", state.edd, Modifier.weight(1f)) { state.edd = it }
                    DateField("USG EDD", state.usgEdd, Modifier.weight(1f)) { state.usgEdd = it }
                }
                MedtrackSectionTitle(title = "RCH")
                ToggleRow(
                    label = "Bypass RCH for now",
                    help = "Skip the number; a reminder task is created.",
                    checked = state.rchBypass,
                    onChange = { state.rchBypass = it },
                )
                if (!state.rchBypass) {
                    TextField("RCH number", state.rchNumber, keyboard = KeyboardType.Number) {
                        state.rchNumber = it.filter(Char::isDigit)
                    }
                }
                if (state.highRisk) {
                    MedtrackSectionTitle(title = "ANC high-risk reasons")
                    MultiSelectChips(state.metadata.ancHighRiskReasons, state.ancReasons, { state.toggleAncReason(it) }, MedtrackColors.Danger)
                }
            }
            category.name.isSurgery() -> {
                MedtrackSectionTitle(title = "Surgical pathway")
                DropdownField("Pathway", state.surgicalPathway, state.metadata.surgicalPathways, { state.surgicalPathway = it })
                when (state.surgicalPathway) {
                    "PLANNED_SURGERY" -> DateField("Surgery date", state.surgeryDate) { state.surgeryDate = it }
                    "SURVEILLANCE" -> DateField("Review date", state.reviewDate) { state.reviewDate = it }
                }
            }
            else -> {
                MedtrackSectionTitle(title = "Review schedule")
                DropdownField("Review frequency", state.reviewFrequency, state.metadata.reviewFrequencies, { state.reviewFrequency = it }, optional = true)
                DateField("Review date", state.reviewDate) { state.reviewDate = it }
            }
        }
    }
}

@Composable
private fun ReviewStep(state: CaseFormState) {
    val category = state.category
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Surface(
            shape = RoundedCornerShape(16.dp),
            color = MedtrackColors.Card,
            border = BorderStroke(1.dp, MedtrackColors.Border),
        ) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                ReviewRow("Patient", state.reviewPatientLine())
                ReviewRow("Category", category?.name ?: "-")
                state.subcategoryLabel()?.let { ReviewRow("Subcategory", it) }
                ReviewRow("Diagnosis", state.diagnosis.ifBlank { "-" })
                if (state.highRisk) ReviewRow("Risk", "High risk")
                state.pathwaySummary()?.let { ReviewRow("Pathway", it) }
            }
        }
        Text(
            "Creating the case saves it on the server and seeds its starter tasks.",
            color = MedtrackColors.Muted,
            style = MaterialTheme.typography.bodySmall,
        )
    }
}

@Composable
private fun ReviewRow(label: String, value: String) {
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(
            label,
            color = MedtrackColors.Faint,
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.ExtraBold,
            modifier = Modifier.width(92.dp),
        )
        Text(
            value,
            color = MedtrackColors.Ink,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.weight(1f),
        )
    }
}

/* ----------------------------- Reusable fields ----------------------------- */

@Composable
private fun FieldRow(content: @Composable () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalAlignment = Alignment.Top,
    ) { content() }
}

@Composable
private fun FieldShell(
    label: String,
    modifier: Modifier = Modifier,
    focused: Boolean = false,
    onClick: (() -> Unit)? = null,
    trailing: (@Composable () -> Unit)? = null,
    content: @Composable () -> Unit,
) {
    val borderColor = if (focused) MedtrackColors.Primary else MedtrackColors.Border
    Surface(
        modifier = modifier
            .height(FieldHeight)
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier),
        shape = RoundedCornerShape(14.dp),
        color = MedtrackColors.Card,
        border = BorderStroke(1.5.dp, borderColor),
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 13.dp, vertical = 9.dp),
            verticalArrangement = Arrangement.spacedBy(3.dp),
        ) {
            Text(
                label,
                color = if (focused) MedtrackColors.Primary else MedtrackColors.Faint,
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.ExtraBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Box(Modifier.weight(1f)) { content() }
                trailing?.invoke()
            }
        }
    }
}

@Composable
private fun TextField(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
    optional: Boolean = false,
    keyboard: KeyboardType = KeyboardType.Text,
    onValueChange: (String) -> Unit,
) {
    var focused by remember { mutableStateOf(false) }
    FieldShell(label = if (optional) "$label (optional)" else label, modifier = modifier, focused = focused) {
        BasicTextField(
            value = value,
            onValueChange = onValueChange,
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = keyboard),
            textStyle = MaterialTheme.typography.bodyMedium.copy(color = MedtrackColors.Ink, fontWeight = FontWeight.Bold),
            cursorBrush = SolidColor(MedtrackColors.Primary),
            modifier = Modifier
                .fillMaxWidth()
                .onFocusChanged { focused = it.isFocused },
        )
    }
}

@Composable
private fun MultilineField(
    label: String,
    value: String,
    optional: Boolean = false,
    onValueChange: (String) -> Unit,
) {
    var focused by remember { mutableStateOf(false) }
    val borderColor = if (focused) MedtrackColors.Primary else MedtrackColors.Border
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        color = MedtrackColors.Card,
        border = BorderStroke(1.5.dp, borderColor),
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 13.dp, vertical = 9.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(
                if (optional) "$label (optional)" else label,
                color = if (focused) MedtrackColors.Primary else MedtrackColors.Faint,
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.ExtraBold,
            )
            BasicTextField(
                value = value,
                onValueChange = onValueChange,
                textStyle = MaterialTheme.typography.bodyMedium.copy(color = MedtrackColors.Ink, fontWeight = FontWeight.Medium),
                cursorBrush = SolidColor(MedtrackColors.Primary),
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 38.dp)
                    .onFocusChanged { focused = it.isFocused },
            )
        }
    }
}

@Composable
private fun ReadonlyField(label: String, value: String, tint: Color) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .height(FieldHeight),
        shape = RoundedCornerShape(14.dp),
        color = tint.copy(alpha = 0.08f),
        border = BorderStroke(1.dp, tint.copy(alpha = 0.28f)),
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 13.dp, vertical = 9.dp),
            verticalArrangement = Arrangement.spacedBy(3.dp),
        ) {
            Text(label, color = MedtrackColors.Faint, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.ExtraBold)
            Text(value, color = tint, style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.ExtraBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

@Composable
@OptIn(ExperimentalMaterial3Api::class)
private fun DropdownField(
    label: String,
    value: String,
    options: List<FormChoice>,
    onSelect: (String) -> Unit,
    modifier: Modifier = Modifier,
    optional: Boolean = false,
) {
    var expanded by remember { mutableStateOf(false) }
    val selectedLabel = options.firstOrNull { it.value == value }?.label
    Box(modifier = modifier) {
        FieldShell(
            label = if (optional) "$label (optional)" else label,
            focused = expanded,
            onClick = { expanded = true },
            trailing = { Icon(Icons.Outlined.ExpandMore, contentDescription = null, tint = MedtrackColors.Faint, modifier = Modifier.size(20.dp)) },
        ) {
            Text(
                selectedLabel ?: "Select",
                color = if (selectedLabel == null) MedtrackColors.Faint else MedtrackColors.Ink,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Bold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach { option ->
                DropdownMenuItem(
                    text = { Text(option.label) },
                    onClick = {
                        onSelect(option.value)
                        expanded = false
                    },
                )
            }
        }
    }
}

@Composable
private fun GplaField(label: String, value: Int?, onSelect: (Int?) -> Unit, modifier: Modifier = Modifier) {
    val options = remember { (0..10).map { FormChoice(it.toString(), it.toString()) } }
    DropdownField(label, value?.toString() ?: "", options, { onSelect(it.toIntOrNull()) }, modifier)
}

@Composable
@OptIn(ExperimentalMaterial3Api::class)
private fun DateField(label: String, value: String, modifier: Modifier = Modifier, onChange: (String) -> Unit) {
    var open by remember { mutableStateOf(false) }
    FieldShell(label = label, modifier = modifier, onClick = { open = true }) {
        Text(
            value.ifBlank { "Select date" },
            color = if (value.isBlank()) MedtrackColors.Faint else MedtrackColors.Ink,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
        )
    }
    if (open) {
        val pickerState = rememberDatePickerState()
        DatePickerDialog(
            onDismissRequest = { open = false },
            confirmButton = {
                TextButton(onClick = {
                    pickerState.selectedDateMillis?.let { onChange(it.toIsoDate()) }
                    open = false
                }) { Text("OK") }
            },
            dismissButton = { TextButton(onClick = { open = false }) { Text("Cancel") } },
        ) { DatePicker(state = pickerState) }
    }
}

@Composable
private fun SearchField(value: String, onValueChange: (String) -> Unit) {
    var focused by remember { mutableStateOf(false) }
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .height(54.dp),
        shape = RoundedCornerShape(14.dp),
        color = MedtrackColors.Card,
        border = BorderStroke(1.5.dp, if (focused) MedtrackColors.Primary else MedtrackColors.Border),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Icon(Icons.Outlined.Search, contentDescription = null, tint = MedtrackColors.Primary, modifier = Modifier.size(20.dp))
            Box(Modifier.weight(1f)) {
                if (value.isBlank()) {
                    Text("Search UHID, name or phone", color = MedtrackColors.Faint, style = MaterialTheme.typography.bodyMedium)
                }
                BasicTextField(
                    value = value,
                    onValueChange = onValueChange,
                    singleLine = true,
                    textStyle = MaterialTheme.typography.bodyMedium.copy(color = MedtrackColors.Ink, fontWeight = FontWeight.Bold),
                    cursorBrush = SolidColor(MedtrackColors.Primary),
                    modifier = Modifier
                        .fillMaxWidth()
                        .onFocusChanged { focused = it.isFocused },
                )
            }
        }
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun MultiSelectChips(options: List<FormChoice>, selected: Set<String>, onToggle: (String) -> Unit, tint: Color) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        options.forEach { option ->
            ChoicePill(option.label, option.value in selected, tint) { onToggle(option.value) }
        }
    }
}

@Composable
private fun ChoicePill(label: String, selected: Boolean, tint: Color, onClick: () -> Unit) {
    Surface(
        modifier = Modifier.clickable(onClick = onClick),
        shape = RoundedCornerShape(50),
        color = if (selected) tint else MedtrackColors.Card,
        border = BorderStroke(1.dp, if (selected) tint else MedtrackColors.Border),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 7.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (selected) Icon(Icons.Outlined.Check, contentDescription = null, tint = Color.White, modifier = Modifier.size(15.dp))
            Text(
                label,
                color = if (selected) Color.White else MedtrackColors.InkSoft,
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

@Composable
private fun SegmentedToggle(options: List<Pair<String, String>>, selected: String, onSelect: (String) -> Unit) {
    Surface(shape = RoundedCornerShape(14.dp), color = MedtrackColors.SurfaceAlt, modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.padding(4.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            options.forEach { (label, value) ->
                val active = value == selected
                Surface(
                    modifier = Modifier
                        .weight(1f)
                        .clickable { onSelect(value) },
                    shape = RoundedCornerShape(11.dp),
                    color = if (active) MedtrackColors.Card else Color.Transparent,
                    border = if (active) BorderStroke(1.dp, MedtrackColors.Border) else null,
                ) {
                    Box(Modifier.padding(vertical = 10.dp), contentAlignment = Alignment.Center) {
                        Text(
                            label,
                            color = if (active) MedtrackColors.Ink else MedtrackColors.Muted,
                            style = MaterialTheme.typography.labelLarge,
                            fontWeight = FontWeight.ExtraBold,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun ToggleRow(label: String, help: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onChange(!checked) },
        shape = RoundedCornerShape(14.dp),
        color = MedtrackColors.Card,
        border = BorderStroke(1.dp, if (checked) MedtrackColors.Primary else MedtrackColors.Border),
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(label, color = MedtrackColors.Ink, fontWeight = FontWeight.Bold)
                Text(help, color = MedtrackColors.Faint, style = MaterialTheme.typography.bodySmall)
            }
            Surface(
                modifier = Modifier.size(width = 46.dp, height = 28.dp),
                shape = RoundedCornerShape(50),
                color = if (checked) MedtrackColors.Primary else MedtrackColors.Border,
            ) {
                Box(contentAlignment = if (checked) Alignment.CenterEnd else Alignment.CenterStart) {
                    Surface(
                        modifier = Modifier
                            .padding(3.dp)
                            .size(22.dp),
                        shape = RoundedCornerShape(50),
                        color = Color.White,
                    ) {}
                }
            }
        }
    }
}

@Composable
private fun BannerError(text: String) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .padding(start = 16.dp, end = 16.dp, top = 8.dp),
        shape = RoundedCornerShape(13.dp),
        color = MedtrackColors.DangerSoft,
        border = BorderStroke(1.dp, MedtrackColors.Danger.copy(alpha = 0.4f)),
    ) {
        Text(
            text,
            modifier = Modifier.padding(13.dp),
            color = MedtrackColors.Danger,
            style = MaterialTheme.typography.bodySmall,
            fontWeight = FontWeight.SemiBold,
        )
    }
}

@Composable
private fun BottomBar(
    primaryLabel: String,
    submitting: Boolean,
    showBack: Boolean,
    onBack: () -> Unit,
    onPrimary: () -> Unit,
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = MedtrackColors.Card,
        border = BorderStroke(1.dp, MedtrackColors.Border.copy(alpha = 0.72f)),
    ) {
        Row(
            modifier = Modifier.padding(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 16.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            if (showBack) {
                Surface(
                    modifier = Modifier
                        .size(52.dp)
                        .clickable(onClick = onBack),
                    shape = RoundedCornerShape(14.dp),
                    color = MedtrackColors.Card,
                    border = BorderStroke(1.dp, MedtrackColors.Border),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "Back", tint = MedtrackColors.InkSoft, modifier = Modifier.size(20.dp))
                    }
                }
            }
            Surface(
                modifier = Modifier
                    .weight(1f)
                    .height(52.dp)
                    .clickable(enabled = !submitting, onClick = onPrimary),
                shape = RoundedCornerShape(14.dp),
                color = MedtrackColors.Primary,
            ) {
                Row(Modifier.fillMaxSize(), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
                    if (submitting) {
                        CircularProgressIndicator(color = Color.White, strokeWidth = 2.dp, modifier = Modifier.size(18.dp))
                    } else {
                        Text(primaryLabel, color = Color.White, fontWeight = FontWeight.ExtraBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Spacer(Modifier.width(7.dp))
                        Icon(Icons.AutoMirrored.Outlined.ArrowForward, contentDescription = null, tint = Color.White, modifier = Modifier.size(19.dp))
                    }
                }
            }
        }
    }
}

@Composable
private fun Stepper(steps: List<String>, currentStep: Int) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(start = 16.dp, end = 16.dp, bottom = 10.dp),
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
                        Icon(Icons.Outlined.Check, contentDescription = null, tint = Color.White, modifier = Modifier.size(15.dp))
                    } else {
                        Text((index + 1).toString(), color = if (current) Color.White else MedtrackColors.Faint, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.ExtraBold)
                    }
                }
            }
            if (current) {
                Text(label, color = MedtrackColors.Ink, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.ExtraBold)
            }
            if (index < steps.lastIndex) {
                Box(
                    modifier = Modifier
                        .weight(1f)
                        .height(2.dp)
                        .background(if (done) MedtrackColors.Success else MedtrackColors.Border, RoundedCornerShape(2.dp)),
                )
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
        Box(modifier = Modifier.clickable(onClick = onClick), contentAlignment = Alignment.Center) { content() }
    }
}

@Composable
private fun CategoryChip(label: String, color: Color) {
    Surface(
        shape = RoundedCornerShape(50),
        color = color.copy(alpha = 0.12f),
        border = BorderStroke(1.dp, color.copy(alpha = 0.24f)),
    ) {
        Text(
            label,
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 5.dp),
            color = color,
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.Bold,
        )
    }
}

@Composable
private fun CenterState(title: String, subtitle: String?, onBack: () -> Unit, loading: Boolean = false) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MedtrackColors.Surface)
            .padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        if (loading) {
            CircularProgressIndicator(color = MedtrackColors.Primary)
            Spacer(Modifier.height(14.dp))
        }
        Text(title, color = MedtrackColors.Ink, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.ExtraBold)
        subtitle?.let {
            Spacer(Modifier.height(6.dp))
            Text(it, color = MedtrackColors.Muted, style = MaterialTheme.typography.bodyMedium)
        }
        Spacer(Modifier.height(18.dp))
        TextButton(onClick = onBack) { Text("Go back") }
    }
}

private fun String?.handoffColor(): Color =
    when {
        this == null -> MedtrackColors.Primary
        isAnc() -> MedtrackColors.Anc
        isSurgery() -> MedtrackColors.Surgery
        trim().equals("Medicine", true) -> MedtrackColors.Medicine
        else -> MedtrackColors.Primary
    }

private fun Long.toIsoDate(): String {
    val formatter = SimpleDateFormat("yyyy-MM-dd", Locale.US).apply { timeZone = TimeZone.getTimeZone("UTC") }
    return formatter.format(java.util.Date(this))
}
