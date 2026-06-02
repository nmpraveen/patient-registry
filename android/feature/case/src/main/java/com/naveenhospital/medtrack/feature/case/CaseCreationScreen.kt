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
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TextFieldDefaults
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.naveenhospital.medtrack.core.designsystem.MedtrackColors
import com.naveenhospital.medtrack.core.designsystem.MedtrackSectionTitle
import com.naveenhospital.medtrack.core.domain.model.CaseCategory
import com.naveenhospital.medtrack.core.domain.model.CaseCreateOutcome
import com.naveenhospital.medtrack.core.domain.model.CaseFormCategory
import com.naveenhospital.medtrack.core.domain.model.CaseFormMetadata
import com.naveenhospital.medtrack.core.domain.model.FormChoice
import com.naveenhospital.medtrack.core.domain.model.NewCaseInput
import com.naveenhospital.medtrack.core.domain.model.PatientLookup
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone

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
        loadError != null -> CenterState(title = "Couldn't load the form", subtitle = loadError, onBack = onBack)
        meta == null -> CenterState(title = "Loading form…", subtitle = null, onBack = onBack, loading = true)
        !meta.canCreate -> CenterState(
            title = "No permission",
            subtitle = "Your role can't create cases. Ask an administrator for access.",
            onBack = onBack,
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
@OptIn(ExperimentalLayoutApi::class)
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
    val stepTitles = remember(category?.name) { state.stepTitles() }
    val pathwayColor = category?.name.handoffColor()

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
            CategoryChip(label = category?.name ?: pathwayLabel, color = pathwayColor)
        }

        Stepper(steps = stepTitles, currentStep = step)

        LazyColumn(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth(),
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 18.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                banner?.let { BannerError(it) }
                when (stepTitles.getOrNull(step)) {
                    "Patient" -> PatientStep(state)
                    "Clinical" -> ClinicalStep(state)
                    "ANC", "Surgery", "Medicine" -> PathwayStep(state)
                    else -> ReviewStep(state)
                }
            }
        }

        BottomBar(
            primaryLabel = if (step < stepTitles.lastIndex) "Continue · ${stepTitles[step + 1]}" else "Create case",
            primaryEnabled = !submitting,
            submitting = submitting && step == stepTitles.lastIndex,
            showBack = step > 0,
            onBack = { if (step > 0) step -= 1 },
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

private fun CaseCreateOutcome.ValidationError.bannerText(): String {
    val details = errors.values.flatten().take(4)
    return if (details.isEmpty()) message else details.joinToString("  •  ")
}

/* ----------------------------- Steps ----------------------------- */

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun PatientStep(state: CaseFormState) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        MedtrackSectionTitle(title = "Patient")
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
        OutlinedTextField(
            value = state.patientQuery,
            onValueChange = {
                state.patientQuery = it
                scope.launch {
                    state.searching = true
                    state.patientResults = runCatching { state.searchPatients(it) }.getOrDefault(emptyList())
                    state.searching = false
                }
            },
            label = { Text("Search UHID, name or phone") },
            leadingIcon = { Icon(Icons.Outlined.Search, contentDescription = null) },
            singleLine = true,
            colors = fieldColors(),
            shape = RoundedCornerShape(14.dp),
            modifier = Modifier.fillMaxWidth(),
        )
        if (state.searching) {
            Text("Searching…", color = MedtrackColors.Faint, style = MaterialTheme.typography.bodySmall)
        }
        state.selectedPatient?.let { picked ->
            Surface(
                shape = RoundedCornerShape(14.dp),
                color = MedtrackColors.PrimarySoft,
                border = BorderStroke(1.dp, MedtrackColors.Primary.copy(alpha = 0.4f)),
            ) {
                Column(modifier = Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text(picked.name.ifBlank { "Patient" }, color = MedtrackColors.Ink, fontWeight = FontWeight.ExtraBold)
                    Text("${picked.uhid}  •  ${picked.genderLabel}  •  ${picked.age ?: "-"}y", color = MedtrackColors.Muted, style = MaterialTheme.typography.bodySmall)
                }
            }
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
                Column(modifier = Modifier.padding(13.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
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
            help = "Generate a local ID now; merge the real UHID later.",
            checked = state.useTemporaryUhid,
            onChange = { state.useTemporaryUhid = it },
        )
        if (!state.useTemporaryUhid) {
            MedtrackTextField("UHID", state.uhid) { state.uhid = it }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            DropdownField("Prefix", state.prefix, state.metadata.prefixes, { state.prefix = it }, modifier = Modifier.weight(1f))
            MedtrackTextField("First name", state.firstName, modifier = Modifier.weight(1.6f)) { state.firstName = it }
        }
        MedtrackTextField("Last name", state.lastName) { state.lastName = it }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            DropdownField("Sex", state.gender, state.metadata.genders, { state.gender = it }, modifier = Modifier.weight(1f))
            MedtrackTextField("Age", state.age, keyboard = KeyboardType.Number, modifier = Modifier.weight(0.8f)) {
                state.age = it.filter(Char::isDigit).take(3)
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
            DropdownField("Blood group", state.bloodGroup, state.metadata.bloodGroups, { state.bloodGroup = it }, optional = true, modifier = Modifier.weight(1f))
            MedtrackTextField("Phone", state.phone, keyboard = KeyboardType.Phone, modifier = Modifier.weight(1.3f)) {
                state.phone = it.filter { c -> c.isDigit() }.take(10)
            }
        }
        MedtrackTextField("Place / district", state.place) { state.place = it }
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun ClinicalStep(state: CaseFormState) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        MedtrackSectionTitle(title = "Category")
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            state.metadata.categories.forEach { option ->
                ChoicePill(
                    label = option.name,
                    selected = state.category?.id == option.id,
                    tint = option.name.handoffColor(),
                    onClick = { state.selectCategory(option) },
                )
            }
        }
        val category = state.category
        if (category != null && category.subcategories.isNotEmpty()) {
            DropdownField("Subcategory", state.subcategory, category.subcategories, { state.subcategory = it })
        }
        MedtrackTextField("Diagnosis / reason", state.diagnosis, minHeight = 76.dp) { state.diagnosis = it }
        MedtrackTextField("Referred by", state.referredBy, optional = true) { state.referredBy = it }
        ToggleRow(
            label = "High risk",
            help = "Flag this case for closer follow-up.",
            checked = state.highRisk,
            onChange = { state.highRisk = it },
        )
        MedtrackSectionTitle(title = "Comorbidities (NCD)")
        MultiSelectChips(
            options = state.metadata.ncdFlags,
            selected = state.ncdFlags,
            onToggle = { state.toggleNcd(it) },
            tint = MedtrackColors.Medicine,
        )
        MedtrackTextField("Notes", state.notes, optional = true, minHeight = 70.dp) { state.notes = it }
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
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                    GplaField("G", state.gravida, { state.gravida = it }, Modifier.weight(1f))
                    GplaField("P", state.para, { state.para = it }, Modifier.weight(1f))
                    GplaField("A", state.abortions, { state.abortions = it }, Modifier.weight(1f))
                    GplaField("L", state.living, { state.living = it }, Modifier.weight(1f))
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                    GplaField("FTND", state.ftnd, { state.ftnd = it }, Modifier.weight(1f))
                    GplaField("LSCS", state.lscs, { state.lscs = it }, Modifier.weight(1f))
                }
                MedtrackSectionTitle(title = "Dates")
                DateField("LMP", state.lmp) { state.lmp = it }
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                    Box(Modifier.weight(1f)) { DateField("EDD", state.edd) { state.edd = it } }
                    Box(Modifier.weight(1f)) { DateField("USG EDD", state.usgEdd) { state.usgEdd = it } }
                }
                MedtrackSectionTitle(title = "RCH")
                ToggleRow(
                    label = "Bypass RCH for now",
                    help = "Skip the RCH number; a reminder task is created.",
                    checked = state.rchBypass,
                    onChange = { state.rchBypass = it },
                )
                if (!state.rchBypass) {
                    MedtrackTextField("RCH number", state.rchNumber, keyboard = KeyboardType.Number) {
                        state.rchNumber = it.filter(Char::isDigit)
                    }
                }
                if (state.highRisk) {
                    MedtrackSectionTitle(title = "ANC high-risk reasons")
                    MultiSelectChips(
                        options = state.metadata.ancHighRiskReasons,
                        selected = state.ancReasons,
                        onToggle = { state.toggleAncReason(it) },
                        tint = MedtrackColors.Danger,
                    )
                }
            }
            category.name.isSurgery() -> {
                MedtrackSectionTitle(title = "Surgical pathway")
                DropdownField("Pathway", state.surgicalPathway, state.metadata.surgicalPathways, { state.surgicalPathway = it })
                if (state.surgicalPathway == "PLANNED_SURGERY") {
                    DateField("Surgery date", state.surgeryDate) { state.surgeryDate = it }
                } else if (state.surgicalPathway == "SURVEILLANCE") {
                    DateField("Review date", state.reviewDate) { state.reviewDate = it }
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
        MedtrackSectionTitle(title = "Review")
        Surface(
            shape = RoundedCornerShape(16.dp),
            color = MedtrackColors.Card,
            border = BorderStroke(1.dp, MedtrackColors.Border),
        ) {
            Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                ReviewRow("Patient", state.reviewPatientLine())
                ReviewRow("Category", category?.name ?: "-")
                state.subcategoryLabel()?.let { ReviewRow("Subcategory", it) }
                ReviewRow("Diagnosis", state.diagnosis.ifBlank { "-" })
                if (state.highRisk) ReviewRow("Risk", "High risk")
                state.pathwaySummary()?.let { ReviewRow("Pathway", it) }
            }
        }
        Text(
            "Submitting creates the case on the server and seeds its starter tasks.",
            color = MedtrackColors.Muted,
            style = MaterialTheme.typography.bodySmall,
        )
    }
}

@Composable
private fun ReviewRow(label: String, value: String) {
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(label, color = MedtrackColors.Faint, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.ExtraBold, modifier = Modifier.width(96.dp))
        Text(value, color = MedtrackColors.Ink, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
    }
}

/* ----------------------------- Reusable fields ----------------------------- */

@Composable
private fun MedtrackTextField(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
    optional: Boolean = false,
    keyboard: KeyboardType = KeyboardType.Text,
    minHeight: androidx.compose.ui.unit.Dp = 0.dp,
    onValueChange: (String) -> Unit,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text(if (optional) "$label (optional)" else label) },
        singleLine = minHeight == 0.dp,
        keyboardOptions = KeyboardOptions(keyboardType = keyboard),
        colors = fieldColors(),
        shape = RoundedCornerShape(14.dp),
        modifier = modifier
            .fillMaxWidth()
            .let { if (minHeight > 0.dp) it.height(minHeight) else it },
    )
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
    val selectedLabel = options.firstOrNull { it.value == value }?.label ?: ""
    Box(modifier = modifier) {
        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .clickable { expanded = true },
            shape = RoundedCornerShape(14.dp),
            color = MedtrackColors.Card,
            border = BorderStroke(1.5.dp, if (expanded) MedtrackColors.Primary else MedtrackColors.Border),
        ) {
            Column(modifier = Modifier.padding(horizontal = 13.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    if (optional) "$label (optional)" else label,
                    color = MedtrackColors.Faint,
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.ExtraBold,
                )
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        selectedLabel.ifBlank { "Select" },
                        color = if (selectedLabel.isBlank()) MedtrackColors.Faint else MedtrackColors.Ink,
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Bold,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f),
                    )
                    Icon(Icons.Outlined.ExpandMore, contentDescription = null, tint = MedtrackColors.Faint, modifier = Modifier.size(20.dp))
                }
            }
        }
        androidx.compose.material3.DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach { option ->
                androidx.compose.material3.DropdownMenuItem(
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
    DropdownField(
        label = label,
        value = value?.toString() ?: "",
        options = options,
        onSelect = { onSelect(it.toIntOrNull()) },
        modifier = modifier,
    )
}

@Composable
@OptIn(ExperimentalMaterial3Api::class)
private fun DateField(label: String, value: String, onChange: (String) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { open = true },
        shape = RoundedCornerShape(14.dp),
        color = MedtrackColors.Card,
        border = BorderStroke(1.5.dp, MedtrackColors.Border),
    ) {
        Column(modifier = Modifier.padding(horizontal = 13.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(label, color = MedtrackColors.Faint, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.ExtraBold)
            Text(
                value.ifBlank { "Select date" },
                color = if (value.isBlank()) MedtrackColors.Faint else MedtrackColors.Ink,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Bold,
            )
        }
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
        ) {
            DatePicker(state = pickerState)
        }
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun MultiSelectChips(options: List<FormChoice>, selected: Set<String>, onToggle: (String) -> Unit, tint: Color) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        options.forEach { option ->
            ChoicePill(label = option.label, selected = option.value in selected, tint = tint, onClick = { onToggle(option.value) })
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
            if (selected) {
                Icon(Icons.Outlined.Check, contentDescription = null, tint = Color.White, modifier = Modifier.size(15.dp))
            }
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
    Surface(
        shape = RoundedCornerShape(14.dp),
        color = MedtrackColors.SurfaceAlt,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(modifier = Modifier.padding(4.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
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
                    Box(modifier = Modifier.padding(vertical = 10.dp), contentAlignment = Alignment.Center) {
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
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
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
            .padding(bottom = 4.dp),
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
    primaryEnabled: Boolean,
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
                        .height(52.dp)
                        .clickable(onClick = onBack),
                    shape = RoundedCornerShape(14.dp),
                    color = MedtrackColors.Card,
                    border = BorderStroke(1.dp, MedtrackColors.Border),
                ) {
                    Row(modifier = Modifier.padding(horizontal = 18.dp).fillMaxSize(), verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "Back", tint = MedtrackColors.InkSoft, modifier = Modifier.size(18.dp))
                    }
                }
            }
            Surface(
                modifier = Modifier
                    .weight(1f)
                    .height(52.dp)
                    .clickable(enabled = primaryEnabled, onClick = onPrimary),
                shape = RoundedCornerShape(14.dp),
                color = if (primaryEnabled) MedtrackColors.Primary else MedtrackColors.Faint,
            ) {
                Row(modifier = Modifier.fillMaxSize(), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
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

@Composable
private fun fieldColors() = TextFieldDefaults.colors(
    focusedContainerColor = MedtrackColors.Card,
    unfocusedContainerColor = MedtrackColors.Card,
    focusedIndicatorColor = MedtrackColors.Primary,
    unfocusedIndicatorColor = MedtrackColors.Border,
)

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
