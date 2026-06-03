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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.ArrowForward
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.Check
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material.icons.outlined.Remove
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
import com.naveenhospital.medtrack.core.domain.model.CaseEditOutcome
import com.naveenhospital.medtrack.core.domain.model.CaseEditPrefill
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
        else -> {
            val state = remember(meta) { CaseFormState(meta, initialCategory) }
            CaseFormScaffold(
                state = state,
                screenTitle = "New case",
                finalActionLabel = "Create case",
                searchPatients = searchPatients,
                onBack = onBack,
                onSubmit = { input, onResult ->
                    scope.launch {
                        val outcome = runCatching { submit(input) }.getOrElse {
                            CaseCreateOutcome.Failure(it.message ?: "Network error. Try again.")
                        }
                        onResult(
                            when (outcome) {
                                is CaseCreateOutcome.Success -> CaseSubmitResult.Success(outcome.caseId, outcome.message)
                                is CaseCreateOutcome.ValidationError -> CaseSubmitResult.Banner(outcome.bannerText())
                                is CaseCreateOutcome.Failure -> CaseSubmitResult.Banner(outcome.message)
                            },
                        )
                    }
                },
                onDone = onCreated,
                modifier = modifier,
            )
        }
    }
}

@Composable
private fun CaseFormScaffold(
    state: CaseFormState,
    screenTitle: String,
    finalActionLabel: String,
    searchPatients: suspend (String) -> List<PatientLookup>,
    onBack: () -> Unit,
    onSubmit: (NewCaseInput, (CaseSubmitResult) -> Unit) -> Unit,
    onDone: (Long, String) -> Unit,
    modifier: Modifier = Modifier,
) {
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
                text = screenTitle,
                modifier = Modifier.weight(1f),
                color = MedtrackColors.Ink,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.ExtraBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            CategoryChip(category?.name ?: screenTitle, pathwayColor)
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
                    "Clinical" -> ClinicalStep(state)
                    "ANC", "Surgery", "Medicine" -> PathwayStep(state)
                    else -> ReviewStep(state)
                }
            }
        }

        // Fixed bottom area: banner (always visible) + buttons
        Column(modifier = Modifier.fillMaxWidth()) {
            banner?.let { BannerError(it) }
            BottomBar(
                primaryLabel = if (step < stepTitles.lastIndex) "Continue" else finalActionLabel,
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
                        onSubmit(state.toInput()) { result ->
                            submitting = false
                            when (result) {
                                is CaseSubmitResult.Success -> onDone(result.caseId, result.message)
                                is CaseSubmitResult.Banner -> banner = result.text
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

private fun CaseEditOutcome.ValidationError.bannerText(): String {
    val details = errors.values.flatten().take(3)
    return if (details.isEmpty()) message else details.joinToString("  •  ")
}

internal sealed interface CaseSubmitResult {
    data class Success(val caseId: Long, val message: String) : CaseSubmitResult
    data class Banner(val text: String) : CaseSubmitResult
}

internal val caseStatusChoices = listOf(
    FormChoice("ACTIVE", "Active"),
    FormChoice("COMPLETED", "Completed"),
    FormChoice("CANCELLED", "Cancelled"),
    FormChoice("LOSS_TO_FOLLOW_UP", "Loss to follow-up"),
)

@Composable
fun CaseEditScreen(
    loadPrefill: suspend () -> CaseEditPrefill,
    searchPatients: suspend (String) -> List<PatientLookup>,
    submit: suspend (NewCaseInput) -> CaseEditOutcome,
    onBack: () -> Unit,
    onSaved: (Long, String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val scope = rememberCoroutineScope()
    var prefill by remember { mutableStateOf<CaseEditPrefill?>(null) }
    var loadError by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        runCatching { loadPrefill() }
            .onSuccess { prefill = it }
            .onFailure { loadError = it.message ?: "Unable to load case" }
    }

    val data = prefill
    when {
        loadError != null -> CenterState("Couldn't load the case", loadError, onBack)
        data == null -> CenterState("Loading case…", null, onBack, loading = true)
        !data.canEdit -> CenterState(
            "No permission",
            "Your role can't edit cases. Ask an administrator for access.",
            onBack,
        )
        else -> {
            val state = remember(data) {
                CaseFormState(data.metadata, CaseCategory.OTHER).apply { applyPrefill(data) }
            }
            CaseFormScaffold(
                state = state,
                screenTitle = "Edit case",
                finalActionLabel = "Save changes",
                searchPatients = searchPatients,
                onBack = onBack,
                onSubmit = { input, onResult ->
                    scope.launch {
                        val outcome = runCatching { submit(input) }.getOrElse {
                            CaseEditOutcome.Failure(it.message ?: "Network error. Try again.")
                        }
                        onResult(
                            when (outcome) {
                                is CaseEditOutcome.Success -> CaseSubmitResult.Success(outcome.caseId, outcome.message)
                                is CaseEditOutcome.ValidationError -> CaseSubmitResult.Banner(outcome.bannerText())
                                is CaseEditOutcome.Failure -> CaseSubmitResult.Banner(outcome.message)
                            },
                        )
                    }
                },
                onDone = onSaved,
                modifier = modifier,
            )
        }
    }
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
            TextField("UHID", state.uhid, required = true) { state.uhid = it }
        }
        FieldRow {
            DropdownField("Prefix", state.prefix, state.metadata.prefixes, { state.prefix = it }, Modifier.weight(1f), required = true)
            TextField("First name", state.firstName, Modifier.weight(1.6f), required = true) { state.firstName = it }
        }
        TextField("Last name", state.lastName, required = true) { state.lastName = it }
        FieldRow {
            DropdownField("Sex", state.gender, state.metadata.genders, { state.gender = it }, Modifier.weight(1f), required = true)
            TextField("Age", state.age, Modifier.weight(0.8f), required = true, keyboard = KeyboardType.Number) {
                state.age = it.filter(Char::isDigit).take(3)
            }
        }
        FieldRow {
            TextField("Phone", state.phone, Modifier.weight(1.3f), required = true, keyboard = KeyboardType.Phone) {
                state.phone = it.filter(Char::isDigit).take(10)
            }
            DropdownField("Blood group", state.bloodGroup, state.metadata.bloodGroups, { state.bloodGroup = it }, Modifier.weight(1f), optional = true)
        }
        TextField("Place / district", state.place, optional = true) { state.place = it }
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun ClinicalStep(state: CaseFormState) {
    val category = state.category
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (state.isEdit) {
            DropdownField("Case status", state.status, caseStatusChoices, { state.status = it }, required = true)
        }
        if (category != null && category.subcategories.isNotEmpty()) {
            DropdownField("Subcategory", state.subcategory, category.subcategories, { state.subcategory = it }, required = true)
        }
        MultilineField("Diagnosis / reason", state.diagnosis, required = true) { state.diagnosis = it }
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
                MedtrackSectionTitle(title = "Obstetric history (GPAL)")
                ToggleRow(
                    label = "Primi (first pregnancy)",
                    help = "Sets Gravida 1 · Para 0 · Abortions 0 · Living 0.",
                    checked = state.isPrimi(),
                    onChange = { checked ->
                        if (checked) {
                            state.gravida = 1
                            state.para = 0
                            state.abortions = 0
                            state.living = 0
                            state.ftnd = 0
                            state.lscs = 0
                        }
                    },
                )
                FieldRow {
                    StepperField("Gravida (G)", state.gravida, { state.gravida = it }, Modifier.weight(1f))
                    StepperField("Para (P)", state.para, { state.para = it }, Modifier.weight(1f))
                }
                FieldRow {
                    StepperField("Abortions (A)", state.abortions, { state.abortions = it }, Modifier.weight(1f))
                    StepperField("Living (L)", state.living, { state.living = it }, Modifier.weight(1f))
                }
                if (state.showsDeliveryModes()) {
                    MedtrackSectionTitle(
                        title = "Mode of previous deliveries",
                        trailing = "Must equal Para (${state.para ?: 0})",
                    )
                    FieldRow {
                        StepperField("Vaginal (FTND)", state.ftnd, { state.ftnd = it }, Modifier.weight(1f))
                        StepperField("C-section (LSCS)", state.lscs, { state.lscs = it }, Modifier.weight(1f))
                    }
                }
                ObstetricSummaryText(state)
                MedtrackSectionTitle(title = "Pregnancy dates")
                DateField("LMP", state.lmp, required = true) { state.lmp = it }
                val eddNeeded = state.edd.isBlank() && state.usgEdd.isBlank()
                FieldRow {
                    DateField("EDD", state.edd, Modifier.weight(1f), required = eddNeeded || state.edd.isNotBlank()) { state.edd = it }
                    DateField("USG EDD", state.usgEdd, Modifier.weight(1f), required = eddNeeded || state.usgEdd.isNotBlank()) { state.usgEdd = it }
                }
                MedtrackSectionTitle(title = "RCH")
                ToggleRow(
                    label = "Bypass RCH for now",
                    help = "Skip the number; a reminder task is created.",
                    checked = state.rchBypass,
                    onChange = { state.rchBypass = it },
                )
                if (!state.rchBypass) {
                    TextField("RCH number", state.rchNumber, required = true, keyboard = KeyboardType.Number) {
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
                DropdownField("Pathway", state.surgicalPathway, state.metadata.surgicalPathways, { state.surgicalPathway = it }, required = true)
                when (state.surgicalPathway) {
                    "PLANNED_SURGERY" -> DateField("Surgery date", state.surgeryDate, required = true) { state.surgeryDate = it }
                    "SURVEILLANCE" -> DateField("Review date", state.reviewDate, required = true) { state.reviewDate = it }
                }
            }
            else -> {
                MedtrackSectionTitle(title = "Review schedule")
                DropdownField("Review frequency", state.reviewFrequency, state.metadata.reviewFrequencies, { state.reviewFrequency = it }, optional = true)
                DateField("Review date", state.reviewDate, required = true) { state.reviewDate = it }
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
            if (state.isEdit) {
                "Saving updates this case on the server."
            } else {
                "Creating the case saves it on the server and seeds its starter tasks."
            },
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
internal fun FieldRow(content: @Composable () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalAlignment = Alignment.Top,
    ) { content() }
}

private enum class FieldStatus { Neutral, Needs, Done }

private fun fieldStatus(required: Boolean, filled: Boolean): FieldStatus =
    when {
        !required -> FieldStatus.Neutral
        filled -> FieldStatus.Done
        else -> FieldStatus.Needs
    }

@Composable
private fun StatusMark(status: FieldStatus) {
    when (status) {
        FieldStatus.Needs -> Box(
            modifier = Modifier
                .size(6.dp)
                .background(MedtrackColors.Warning.copy(alpha = 0.85f), CircleShape),
        )
        FieldStatus.Done -> Icon(
            Icons.Outlined.Check,
            contentDescription = null,
            tint = MedtrackColors.Success,
            modifier = Modifier.size(13.dp),
        )
        FieldStatus.Neutral -> Unit
    }
}

@Composable
private fun FieldLabel(label: String, focused: Boolean, status: FieldStatus) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
        Text(
            label,
            color = if (focused) MedtrackColors.Primary else MedtrackColors.Faint,
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.ExtraBold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
        StatusMark(status)
    }
}

@Composable
private fun FieldShell(
    label: String,
    modifier: Modifier = Modifier,
    focused: Boolean = false,
    status: FieldStatus = FieldStatus.Neutral,
    onClick: (() -> Unit)? = null,
    trailing: (@Composable () -> Unit)? = null,
    content: @Composable () -> Unit,
) {
    val borderColor = when {
        focused -> MedtrackColors.Primary
        status == FieldStatus.Needs -> MedtrackColors.Warning.copy(alpha = 0.3f)
        else -> MedtrackColors.Border
    }
    val fill = if (status == FieldStatus.Needs && !focused) {
        MedtrackColors.WarningSoft.copy(alpha = 0.25f)
    } else {
        MedtrackColors.Card
    }
    Surface(
        modifier = modifier
            .height(FieldHeight)
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier),
        shape = RoundedCornerShape(14.dp),
        color = fill,
        border = BorderStroke(1.5.dp, borderColor),
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 13.dp, vertical = 9.dp),
            verticalArrangement = Arrangement.spacedBy(3.dp),
        ) {
            FieldLabel(label, focused, status)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Box(Modifier.weight(1f)) { content() }
                trailing?.invoke()
            }
        }
    }
}

@Composable
internal fun TextField(
    label: String,
    value: String,
    modifier: Modifier = Modifier,
    optional: Boolean = false,
    required: Boolean = false,
    keyboard: KeyboardType = KeyboardType.Text,
    onValueChange: (String) -> Unit,
) {
    var focused by remember { mutableStateOf(false) }
    FieldShell(
        label = if (optional) "$label (optional)" else label,
        modifier = modifier,
        focused = focused,
        status = fieldStatus(required, value.isNotBlank()),
    ) {
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
internal fun MultilineField(
    label: String,
    value: String,
    optional: Boolean = false,
    required: Boolean = false,
    onValueChange: (String) -> Unit,
) {
    var focused by remember { mutableStateOf(false) }
    val status = fieldStatus(required, value.isNotBlank())
    val borderColor = when {
        focused -> MedtrackColors.Primary
        status == FieldStatus.Needs -> MedtrackColors.Warning.copy(alpha = 0.3f)
        else -> MedtrackColors.Border
    }
    val fill = if (status == FieldStatus.Needs && !focused) {
        MedtrackColors.WarningSoft.copy(alpha = 0.25f)
    } else {
        MedtrackColors.Card
    }
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        color = fill,
        border = BorderStroke(1.5.dp, borderColor),
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 13.dp, vertical = 9.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            FieldLabel(if (optional) "$label (optional)" else label, focused, status)
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
@OptIn(ExperimentalMaterial3Api::class)
internal fun DropdownField(
    label: String,
    value: String,
    options: List<FormChoice>,
    onSelect: (String) -> Unit,
    modifier: Modifier = Modifier,
    optional: Boolean = false,
    required: Boolean = false,
) {
    var expanded by remember { mutableStateOf(false) }
    val selectedLabel = options.firstOrNull { it.value == value }?.label
    Box(modifier = modifier) {
        FieldShell(
            label = if (optional) "$label (optional)" else label,
            focused = expanded,
            status = fieldStatus(required, value.isNotBlank()),
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
private fun StepButton(add: Boolean, enabled: Boolean, onClick: () -> Unit) {
    Surface(
        modifier = Modifier
            .size(30.dp)
            .clickable(enabled = enabled, onClick = onClick),
        shape = CircleShape,
        color = if (enabled) MedtrackColors.PrimarySoft else MedtrackColors.SurfaceAlt,
    ) {
        Box(contentAlignment = Alignment.Center) {
            Icon(
                if (add) Icons.Outlined.Add else Icons.Outlined.Remove,
                contentDescription = if (add) "Increase" else "Decrease",
                tint = if (enabled) MedtrackColors.Primary else MedtrackColors.Faint,
                modifier = Modifier.size(17.dp),
            )
        }
    }
}

@Composable
private fun ObstetricSummaryText(state: CaseFormState) {
    val g = state.gravida ?: 0
    val p = state.para ?: 0
    val a = state.abortions ?: 0
    val l = state.living ?: 0
    val summary = buildString {
        append("G$g P$p A$a L$l")
        if (state.showsDeliveryModes()) {
            append("  |  FTND ${state.ftnd ?: 0} LSCS ${state.lscs ?: 0}")
        }
    }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Surface(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(12.dp),
            color = MedtrackColors.PrimarySoft,
        ) {
            Text(
                text = summary,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 9.dp),
                color = MedtrackColors.Primary,
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.ExtraBold,
                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
            )
        }
        if (l > p) {
            Text(
                text = "Living children can exceed Para when there were multiple births.",
                color = MedtrackColors.Muted,
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.Medium,
            )
        }
    }
}

@Composable
private fun StepperField(label: String, value: Int?, onChange: (Int) -> Unit, modifier: Modifier = Modifier) {
    val current = value ?: 0
    Surface(
        modifier = modifier.height(FieldHeight),
        shape = RoundedCornerShape(14.dp),
        color = MedtrackColors.Card,
        border = BorderStroke(1.5.dp, MedtrackColors.Border),
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 7.dp),
            verticalArrangement = Arrangement.spacedBy(2.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                label,
                color = MedtrackColors.Faint,
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.ExtraBold,
                maxLines = 1,
            )
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                StepButton(add = false, enabled = current > 0) { onChange((current - 1).coerceAtLeast(0)) }
                Text(
                    current.toString(),
                    color = MedtrackColors.Ink,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.ExtraBold,
                )
                StepButton(add = true, enabled = current < 10) { onChange((current + 1).coerceAtMost(10)) }
            }
        }
    }
}

@Composable
@OptIn(ExperimentalMaterial3Api::class)
internal fun DateField(label: String, value: String, modifier: Modifier = Modifier, required: Boolean = false, onChange: (String) -> Unit) {
    var open by remember { mutableStateOf(false) }
    FieldShell(label = label, modifier = modifier, status = fieldStatus(required, value.isNotBlank()), onClick = { open = true }) {
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
internal fun BannerError(text: String) {
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
