package com.naveenhospital.medtrack.feature.home

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Chat
import androidx.compose.material.icons.automirrored.outlined.OpenInNew
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.Flag
import androidx.compose.material.icons.outlined.FilterList
import androidx.compose.material.icons.outlined.Notifications
import androidx.compose.material.icons.outlined.Phone
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.naveenhospital.medtrack.core.designsystem.R as DesignR
import com.naveenhospital.medtrack.core.designsystem.MedtrackColors
import com.naveenhospital.medtrack.core.designsystem.MedtrackPullRefreshBox
import com.naveenhospital.medtrack.core.designsystem.MedtrackStatusPill
import com.naveenhospital.medtrack.core.domain.model.CaseCategory
import com.naveenhospital.medtrack.core.domain.model.CaseStatus
import com.naveenhospital.medtrack.core.domain.model.CategoryFilterOption
import com.naveenhospital.medtrack.core.domain.model.InboxStats
import com.naveenhospital.medtrack.core.domain.model.PatientCase
import com.naveenhospital.medtrack.core.domain.model.SubcategoryFilterOption
import androidx.paging.compose.LazyPagingItems
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.roundToInt

private object HomeUiScale {
    val ScreenHorizontalPadding = 8.dp
    val ScreenVerticalPadding = 6.dp
    val SectionGap = 6.dp
    val ListCardGap = 8.dp
    val ListBottomPadding = 104.dp

    val HeaderAvatarSize = 40.dp
    val HeaderButtonSize = 40.dp
    val HeaderButtonRadius = 12.dp
    val HeaderIconSize = 18.dp
    val HeaderDotSize = 7.dp
    val HeaderDateText = 11.sp
    val HeaderGreetingText = 16.sp

    val SearchHeight = 43.dp
    val SearchRadius = 14.dp
    val SearchHorizontalPaddingStart = 10.dp
    val SearchHorizontalPaddingEnd = 5.dp
    val SearchGap = 7.dp
    val SearchIconSize = 18.dp
    val SearchFilterButtonSize = 34.dp
    val SearchFilterButtonRadius = 10.dp
    val SearchText = 12.sp

    val BucketGap = 8.dp
    val BucketHeight = 37.dp
    val BucketHorizontalPadding = 12.dp
    val BucketInnerGap = 7.dp
    val BucketText = 12.sp
    val BucketCountPaddingHorizontal = 6.dp
    val BucketCountPaddingVertical = 2.dp

    val CardRadius = 18.dp
    val CardRailWidth = 7.dp
    val CardHorizontalPadding = 8.dp
    val CardVerticalPadding = 9.dp
    val CardExpandedVerticalPadding = 10.dp
    val CardCollapsedGap = 6.dp
    val CardExpandedGap = 8.dp
    val CardHeaderGap = 10.dp
    val CardTextGap = 4.dp
    val CardNameText = 14.sp
    val CardSummaryText = 12.sp
    val CardMetaText = 12.sp

    val CategoryIconSize = 46.dp
    val CategoryIconRadius = 14.dp
    val CategoryGlyphSize = 26.dp
    val StatusPillPaddingHorizontal = 8.dp
    val StatusPillPaddingVertical = 2.dp
    val DuePillPaddingHorizontal = 6.dp
    val DuePillPaddingVertical = 2.dp
    val RiskFlagSize = 28.dp
    val RiskFlagIconSize = 16.dp

    val VitalPaddingHorizontal = 9.dp
    val VitalPaddingVertical = 5.dp
    val TaskChipPaddingHorizontal = 10.dp
    val TaskChipPaddingVertical = 5.dp
    val ActionButtonHeight = 44.dp
    val ActionIconSize = 17.dp
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
fun HomeScreen(
    cases: LazyPagingItems<PatientCase>,
    stats: InboxStats,
    searchQuery: String,
    selectedBucket: String?,
    selectedScope: String,
    categoryOptions: List<CategoryFilterOption>,
    selectedCategories: Set<String>,
    selectedSubcategories: Set<String>,
    pendingWriteCount: Int,
    isRefreshing: Boolean,
    isLoadingMore: Boolean,
    error: String?,
    actionMessage: String?,
    userDisplayName: String?,
    onSearchChanged: (String) -> Unit,
    onBucketSelected: (String?) -> Unit,
    onScopeSelected: (String) -> Unit,
    onFiltersApplied: (Set<String>, Set<String>) -> Unit,
    onCategoryFilterSelected: (PatientCase) -> Unit,
    onRefresh: () -> Unit,
    onCallPatient: (PatientCase) -> Unit,
    onMessagePatient: (PatientCase) -> Unit,
    onCompleteTask: (PatientCase) -> Unit,
    onOpenCase: (PatientCase) -> Unit,
    onOpenNotifications: () -> Unit,
    onSignOut: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var expandedCaseId by rememberSaveable { mutableStateOf<String?>(null) }
    var riskCase by rememberSaveable { mutableStateOf<PatientCase?>(null) }
    var showFilterSheet by rememberSaveable { mutableStateOf(false) }
    var showSignOutDialog by rememberSaveable { mutableStateOf(false) }
    val listState = rememberLazyListState()

    Column(
        modifier = modifier
            .background(MedtrackColors.Surface)
            .padding(horizontal = HomeUiScale.ScreenHorizontalPadding, vertical = HomeUiScale.ScreenVerticalPadding),
        verticalArrangement = Arrangement.spacedBy(HomeUiScale.SectionGap),
    ) {
        V2aHeader(
            userDisplayName = userDisplayName,
            onOpenNotifications = onOpenNotifications,
            onAccount = { showSignOutDialog = true },
        )

        SearchFilterBar(
            value = searchQuery,
            onValueChange = onSearchChanged,
            onFilterClick = { showFilterSheet = true },
        )

        BucketChips(stats = stats, selectedBucket = selectedBucket, onBucketSelected = onBucketSelected)
        ActiveFilterChips(
            categoryOptions = categoryOptions,
            selectedCategories = selectedCategories,
            selectedSubcategories = selectedSubcategories,
            onFiltersApplied = onFiltersApplied,
        )

        if (error != null) {
            Text(text = error, color = MedtrackColors.Danger)
        }

        if (actionMessage != null) {
            Text(text = actionMessage, color = MedtrackColors.Muted)
        }

        if (pendingWriteCount > 0) {
            MedtrackStatusPill(text = "$pendingWriteCount pending sync", color = MedtrackColors.Warning)
        }

        if (isRefreshing) {
            Text(text = "Refreshing", color = MedtrackColors.Muted)
        }

        ListHeader(
            selectedBucket = selectedBucket,
            itemCount = cases.itemCount,
        )

        MedtrackPullRefreshBox(
            isRefreshing = isRefreshing,
            onRefresh = onRefresh,
            canRefresh = { listState.firstVisibleItemIndex == 0 && listState.firstVisibleItemScrollOffset == 0 },
        ) {
            LazyColumn(
                state = listState,
                verticalArrangement = Arrangement.spacedBy(HomeUiScale.ListCardGap),
                contentPadding = PaddingValues(bottom = HomeUiScale.ListBottomPadding),
            ) {
                if (cases.itemCount == 0 && !isRefreshing) {
                    item {
                        Surface(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(HomeUiScale.CardRadius),
                            color = MedtrackColors.Card,
                            border = androidx.compose.foundation.BorderStroke(1.dp, MedtrackColors.Border),
                        ) {
                            Column(
                                modifier = Modifier.padding(12.dp),
                                verticalArrangement = Arrangement.spacedBy(6.dp),
                            ) {
                                Text(
                                    text = if (searchQuery.isBlank()) "No patients in this view" else "No matching patients",
                                    color = MedtrackColors.Muted,
                                )
                                if (searchQuery.isNotBlank()) {
                                    TextButton(onClick = { onSearchChanged("") }) {
                                        Text("Clear search")
                                    }
                                }
                            }
                        }
                    }
                }
                items(
                    count = cases.itemCount,
                    key = { index -> cases[index]?.id ?: "case-placeholder-$index" },
                ) { index ->
                    val patientCase = cases[index] ?: return@items
                    PatientCard(
                        patientCase = patientCase,
                        selectedBucket = selectedBucket,
                        expanded = expandedCaseId == patientCase.id,
                        onToggle = {
                            expandedCaseId = if (expandedCaseId == patientCase.id) null else patientCase.id
                        },
                        onCallPatient = { onCallPatient(patientCase) },
                        onMessagePatient = { onMessagePatient(patientCase) },
                        onCompleteTask = { onCompleteTask(patientCase) },
                        onOpenCase = { onOpenCase(patientCase) },
                        onCategoryFilter = { onCategoryFilterSelected(patientCase) },
                        onRiskClick = { riskCase = patientCase },
                    )
                }
                if (isLoadingMore) {
                    item {
                        Surface(
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(HomeUiScale.CardRadius),
                            color = MedtrackColors.Card,
                            border = androidx.compose.foundation.BorderStroke(1.dp, MedtrackColors.Border),
                        ) {
                            Text(
                                text = "Loading more",
                                color = MedtrackColors.Muted,
                                modifier = Modifier.padding(14.dp),
                            )
                        }
                    }
                }
            }
        }
    }

    riskCase?.let { patientCase ->
        RiskReasonsSheet(
            patientCase = patientCase,
            onDismiss = { riskCase = null },
        )
    }

    if (showFilterSheet) {
        CategoryFilterSheet(
            categoryOptions = categoryOptions,
            selectedCategories = selectedCategories,
            selectedSubcategories = selectedSubcategories,
            selectedScope = selectedScope,
            onDismiss = { showFilterSheet = false },
            onScopeSelected = onScopeSelected,
            onApply = { categories, subcategories ->
                showFilterSheet = false
                onFiltersApplied(categories, subcategories)
            },
        )
    }

    if (showSignOutDialog) {
        AlertDialog(
            onDismissRequest = { showSignOutDialog = false },
            title = { Text("Sign out") },
            text = { Text("End this mobile session?") },
            confirmButton = {
                TextButton(
                    onClick = {
                        showSignOutDialog = false
                        onSignOut()
                    },
                ) {
                    Text("Sign out")
                }
            },
            dismissButton = {
                TextButton(onClick = { showSignOutDialog = false }) {
                    Text("Cancel")
                }
            },
        )
    }
}

@Composable
private fun V2aHeader(
    userDisplayName: String?,
    onOpenNotifications: () -> Unit,
    onAccount: () -> Unit,
) {
    val greetingName = headerDisplayName(userDisplayName)
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Surface(
            modifier = Modifier
                .size(HomeUiScale.HeaderAvatarSize)
                .clickable(onClick = onAccount),
            shape = RoundedCornerShape(HomeUiScale.HeaderButtonRadius),
            color = MedtrackColors.Primary,
        ) {
            Box(contentAlignment = Alignment.Center) {
                Text(
                    text = avatarInitials(greetingName),
                    color = Color.White,
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.titleSmall,
                )
            }
        }
        Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(1.dp)) {
            Text(
                text = todayStampV2(),
                color = MedtrackColors.Muted,
                style = MaterialTheme.typography.labelSmall.copy(fontSize = HomeUiScale.HeaderDateText),
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = "Hi $greetingName.",
                color = MedtrackColors.Ink,
                style = MaterialTheme.typography.titleMedium.copy(fontSize = HomeUiScale.HeaderGreetingText),
                fontWeight = FontWeight.Bold,
            )
        }
        HeaderIconButton(onClick = onOpenNotifications) {
            Box {
                Icon(
                    imageVector = Icons.Outlined.Notifications,
                    contentDescription = "Alerts",
                    modifier = Modifier.size(HomeUiScale.HeaderIconSize),
                )
                Box(
                    modifier = Modifier
                        .align(Alignment.TopEnd)
                        .size(HomeUiScale.HeaderDotSize)
                        .background(MedtrackColors.Danger, RoundedCornerShape(50)),
                )
            }
        }
    }
}

private fun headerDisplayName(displayName: String?): String =
    displayName
        ?.trim()
        ?.takeIf { it.isNotBlank() }
        ?.let(::titleCaseSimpleName)
        ?: "Staff"

private fun titleCaseSimpleName(name: String): String {
    val locale = Locale.getDefault()
    return name
        .split(Regex("\\s+"))
        .joinToString(" ") { word ->
            if (word.all { it.isLowerCase() } || word.all { it.isUpperCase() }) {
                word.lowercase(locale).replaceFirstChar { it.titlecase(locale) }
            } else {
                word
            }
        }
}

private fun avatarInitials(displayName: String): String {
    val words = displayName
        .trim()
        .split(Regex("\\s+"))
        .filter { it.isNotBlank() }
    val initials = if (words.size >= 2) {
        "${words[0].first()}${words[1].first()}"
    } else {
        words.firstOrNull()?.take(2).orEmpty()
    }
    return initials.uppercase(Locale.getDefault()).ifBlank { "MT" }
}

private fun todayStampV2(): String =
    "${SimpleDateFormat("EEE", Locale.getDefault()).format(Date())} \u2022 ${
        SimpleDateFormat("dd MMM", Locale.getDefault()).format(Date())
    }".uppercase(Locale.getDefault())

private fun todayStamp(): String =
    SimpleDateFormat("EEE • dd MMM", Locale.getDefault()).format(Date()).uppercase(Locale.getDefault())

@Composable
private fun HeaderIconButton(
    onClick: () -> Unit,
    content: @Composable () -> Unit,
) {
    Surface(
        modifier = Modifier.size(HomeUiScale.HeaderButtonSize),
        shape = RoundedCornerShape(HomeUiScale.HeaderButtonRadius),
        color = MedtrackColors.Card,
        border = androidx.compose.foundation.BorderStroke(1.dp, MedtrackColors.Border),
    ) {
        Box(
            modifier = Modifier.clickable(onClick = onClick),
            contentAlignment = Alignment.Center,
        ) {
            content()
        }
    }
}

@Composable
private fun SearchFilterBar(
    value: String,
    onValueChange: (String) -> Unit,
    onFilterClick: () -> Unit,
) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .height(HomeUiScale.SearchHeight),
        shape = RoundedCornerShape(HomeUiScale.SearchRadius),
        color = MedtrackColors.Card,
        border = androidx.compose.foundation.BorderStroke(1.dp, MedtrackColors.Border),
    ) {
        Row(
            modifier = Modifier.padding(
                start = HomeUiScale.SearchHorizontalPaddingStart,
                end = HomeUiScale.SearchHorizontalPaddingEnd,
            ),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(HomeUiScale.SearchGap),
        ) {
            Icon(
                imageVector = Icons.Outlined.Search,
                contentDescription = null,
                tint = MedtrackColors.Muted,
                modifier = Modifier.size(HomeUiScale.SearchIconSize),
            )
            BasicTextField(
                value = value,
                onValueChange = onValueChange,
                singleLine = true,
                textStyle = MaterialTheme.typography.bodySmall.copy(
                    color = MedtrackColors.Ink,
                    fontSize = HomeUiScale.SearchText,
                ),
                modifier = Modifier.weight(1f),
                decorationBox = { innerTextField ->
                    if (value.isBlank()) {
                        Text(
                            text = "Search patient, UHID, phone",
                            color = MedtrackColors.Muted.copy(alpha = 0.72f),
                            style = MaterialTheme.typography.bodySmall.copy(fontSize = HomeUiScale.SearchText),
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                    innerTextField()
                },
            )
            Surface(
                modifier = Modifier.size(HomeUiScale.SearchFilterButtonSize),
                shape = RoundedCornerShape(HomeUiScale.SearchFilterButtonRadius),
                color = MedtrackColors.Surface,
            ) {
                Box(
                    modifier = Modifier.clickable(onClick = onFilterClick),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        imageVector = Icons.Outlined.FilterList,
                        contentDescription = "Filters",
                        tint = MedtrackColors.Ink,
                        modifier = Modifier.size(HomeUiScale.SearchIconSize),
                    )
                }
            }
        }
    }
}

@Composable
private fun ListHeader(
    selectedBucket: String?,
    itemCount: Int,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = "${bucketHeader(selectedBucket)} \u2022 $itemCount ${patientNoun(itemCount).uppercase(Locale.getDefault())}",
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Bold,
            color = MedtrackColors.Muted,
        )
        Text(
            text = "by time",
            style = MaterialTheme.typography.labelSmall,
            color = MedtrackColors.Muted,
        )
    }
}

private fun bucketHeader(bucket: String?): String =
    when (bucket) {
        "today" -> "TODAY"
        "upcoming" -> "UPCOMING"
        "overdue" -> "OVERDUE"
        "awaiting" -> "AWAITING"
        "red" -> "RED"
        else -> "ALL"
    }

private fun patientNoun(count: Int): String =
    if (count == 1) "patient" else "patients"

@Composable
@OptIn(ExperimentalMaterial3Api::class)
private fun RiskReasonsSheet(
    patientCase: PatientCase,
    onDismiss: () -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(sheetState = sheetState, onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(start = 16.dp, end = 16.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(
                text = "Risk reasons",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            patientCase.highRiskReasons.ifEmpty { listOf("Server marked this case as red.") }
                .forEach { reason ->
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(9.dp),
                        verticalAlignment = Alignment.Top,
                    ) {
                        Box(
                            modifier = Modifier
                                .padding(top = 7.dp)
                                .size(8.dp)
                                .background(MedtrackColors.Danger, RoundedCornerShape(50)),
                        )
                        Column(
                            modifier = Modifier.weight(1f),
                            verticalArrangement = Arrangement.spacedBy(4.dp),
                        ) {
                            Text(text = reason, color = MedtrackColors.Ink)
                            MedtrackStatusPill(
                                text = patientCase.riskReasonSource(),
                                color = if (patientCase.category == CaseCategory.ANC) MedtrackColors.Danger else MedtrackColors.Warning,
                            )
                        }
                    }
                }
            TextButton(onClick = onDismiss, modifier = Modifier.align(Alignment.End)) {
                Text("Close")
            }
        }
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun ActiveFilterChips(
    categoryOptions: List<CategoryFilterOption>,
    selectedCategories: Set<String>,
    selectedSubcategories: Set<String>,
    onFiltersApplied: (Set<String>, Set<String>) -> Unit,
) {
    if (selectedCategories.isEmpty() && selectedSubcategories.isEmpty()) return

    val subcategoryOptions = categoryOptions.flatMap { it.subcategories }
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        selectedCategories.forEach { value ->
            val option = categoryOptions.firstOrNull { it.value == value }
            val label = option?.label ?: value
            FilterChip(
                selected = true,
                onClick = { onFiltersApplied(selectedCategories - value, selectedSubcategories) },
                colors = pulseFilterChipColors(option?.let(::categoryOptionColor) ?: MedtrackColors.Primary),
                label = { Text(label) },
            )
        }
        selectedSubcategories.forEach { value ->
            val label = subcategoryOptions.firstOrNull { it.value == value }?.label ?: value
            FilterChip(
                selected = true,
                onClick = { onFiltersApplied(selectedCategories, selectedSubcategories - value) },
                colors = pulseFilterChipColors(),
                label = { Text(label) },
            )
        }
        TextButton(onClick = { onFiltersApplied(emptySet(), emptySet()) }) {
            Text("Clear")
        }
    }
}

@Composable
@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
private fun CategoryFilterSheet(
    categoryOptions: List<CategoryFilterOption>,
    selectedCategories: Set<String>,
    selectedSubcategories: Set<String>,
    selectedScope: String,
    onDismiss: () -> Unit,
    onScopeSelected: (String) -> Unit,
    onApply: (Set<String>, Set<String>) -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var draftCategories by rememberSaveable(selectedCategories.toList()) { mutableStateOf(selectedCategories.toList()) }
    var draftSubcategories by rememberSaveable(selectedSubcategories.toList()) { mutableStateOf(selectedSubcategories.toList()) }
    var draftScope by rememberSaveable(selectedScope) { mutableStateOf(selectedScope) }
    val visibleSubcategories = categoryOptions
        .filter { draftCategories.isEmpty() || it.value in draftCategories }
        .flatMap { it.subcategories }
    val visibleSubcategoryValues = visibleSubcategories.map { it.value }.toSet()

    ModalBottomSheet(sheetState = sheetState, onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(start = 16.dp, end = 16.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = "Filters",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )

            Text(text = "Scope", fontWeight = FontWeight.SemiBold)
            ScopeChips(selectedScope = draftScope, onScopeSelected = { draftScope = it })

            Text(text = "Category", fontWeight = FontWeight.SemiBold)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                categoryOptions.forEach { option ->
                    FilterChip(
                        modifier = Modifier.semantics {
                            contentDescription = "Category filter ${option.label}"
                        },
                        selected = option.value in draftCategories,
                        onClick = {
                            val next = draftCategories.toggle(option.value)
                            draftCategories = next
                            if (next.isNotEmpty()) {
                                val allowed = categoryOptions
                                    .filter { it.value in next }
                                    .flatMap { it.subcategories }
                                    .map { it.value }
                                    .toSet()
                                draftSubcategories = draftSubcategories.filter { it in allowed }
                            }
                        },
                        colors = pulseFilterChipColors(categoryOptionColor(option)),
                        label = { Text(option.label) },
                    )
                }
            }

            if (visibleSubcategories.isNotEmpty()) {
                Text(text = "Sub-category", fontWeight = FontWeight.SemiBold)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    visibleSubcategories.forEach { option ->
                        FilterChip(
                            modifier = Modifier.semantics {
                                contentDescription = "Sub-category filter ${option.label}"
                            },
                            selected = option.value in draftSubcategories,
                            onClick = { draftSubcategories = draftSubcategories.toggle(option.value) },
                            colors = pulseFilterChipColors(),
                            label = { Text(option.label) },
                        )
                    }
                }
            }

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                TextButton(
                    onClick = {
                        draftCategories = emptyList()
                        draftSubcategories = emptyList()
                    },
                    modifier = Modifier.weight(1f),
                ) {
                    Text("Clear")
                }
                Button(
                    onClick = {
                        onScopeSelected(draftScope)
                        onApply(
                            draftCategories.toSet(),
                            draftSubcategories.filter { it in visibleSubcategoryValues || draftCategories.isEmpty() }.toSet(),
                        )
                    },
                    modifier = Modifier.weight(1f),
                ) {
                    Text("Apply")
                }
            }
        }
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun ScopeChips(
    selectedScope: String,
    onScopeSelected: (String) -> Unit,
) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        listOf(
            "me" to "Assigned to me",
            "all" to "All visible",
        ).forEach { (scope, label) ->
            FilterChip(
                selected = selectedScope == scope,
                onClick = { onScopeSelected(scope) },
                colors = pulseFilterChipColors(),
                label = { Text(label) },
            )
        }
    }
}

@Composable
private fun pulseFilterChipColors(accent: Color = MedtrackColors.Primary) = FilterChipDefaults.filterChipColors(
    containerColor = MedtrackColors.Card,
    labelColor = MedtrackColors.Ink,
    selectedContainerColor = accent,
    selectedLabelColor = Color.White,
    selectedLeadingIconColor = Color.White,
)

private fun categoryOptionColor(option: CategoryFilterOption): Color =
    if (option.label.isCustomRehabLabel()) MedtrackColors.CustomRehab else option.category.color()

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun BucketChips(
    stats: InboxStats,
    selectedBucket: String?,
    onBucketSelected: (String?) -> Unit,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(HomeUiScale.BucketGap),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Spacer(modifier = Modifier.width(2.dp))
        listOf(
            BucketFilter("today", "Today", stats.today, MedtrackColors.Primary),
            BucketFilter("upcoming", "Upcoming", stats.upcoming, MedtrackColors.Primary),
            BucketFilter("overdue", "Overdue", stats.overdue, MedtrackColors.Danger),
            BucketFilter("awaiting", "Awaiting", stats.awaiting, MedtrackColors.Warning),
            BucketFilter("red", "Red", stats.red, MedtrackColors.Danger),
        ).forEach { filter ->
            BucketFilterChip(
                selected = selectedBucket == filter.key,
                onClick = { onBucketSelected(if (selectedBucket == filter.key) null else filter.key) },
                label = filter.label,
                count = filter.count,
                accent = filter.accent,
            )
        }
        Spacer(modifier = Modifier.width(2.dp))
    }
}

private data class BucketFilter(
    val key: String,
    val label: String,
    val count: Int,
    val accent: Color,
)

@Composable
private fun BucketFilterChip(
    selected: Boolean,
    label: String,
    count: Int,
    accent: Color,
    onClick: () -> Unit,
) {
    Surface(
        shape = RoundedCornerShape(18.dp),
        color = if (selected) accent else MedtrackColors.Card,
        border = if (selected) null else androidx.compose.foundation.BorderStroke(1.dp, MedtrackColors.Border.copy(alpha = 0.78f)),
        modifier = Modifier
            .height(HomeUiScale.BucketHeight)
            .clickable(onClick = onClick),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = HomeUiScale.BucketHorizontalPadding),
            horizontalArrangement = Arrangement.spacedBy(HomeUiScale.BucketInnerGap),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = label,
                color = if (selected) Color.White else MedtrackColors.Ink,
                style = MaterialTheme.typography.labelMedium.copy(fontSize = HomeUiScale.BucketText),
                fontWeight = FontWeight.Bold,
            )
            Surface(
                shape = RoundedCornerShape(50),
                color = if (selected) Color.White.copy(alpha = 0.18f) else accent.copy(alpha = 0.1f),
                border = if (selected) null else androidx.compose.foundation.BorderStroke(1.dp, accent.copy(alpha = 0.16f)),
            ) {
                Text(
                    text = count.toString(),
                    color = if (selected) Color.White.copy(alpha = 0.86f) else accent,
                    style = MaterialTheme.typography.labelMedium.copy(fontSize = HomeUiScale.BucketText),
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(
                        horizontal = HomeUiScale.BucketCountPaddingHorizontal,
                        vertical = HomeUiScale.BucketCountPaddingVertical,
                    ),
                    maxLines = 1,
                )
            }
        }
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun PatientCard(
    patientCase: PatientCase,
    selectedBucket: String?,
    expanded: Boolean,
    onToggle: () -> Unit,
    onCallPatient: () -> Unit,
    onMessagePatient: () -> Unit,
    onCompleteTask: () -> Unit,
    onOpenCase: () -> Unit,
    onCategoryFilter: () -> Unit,
    onRiskClick: () -> Unit,
) {
    var dragOffset by rememberSaveable(patientCase.id) { mutableStateOf(0f) }
    val density = LocalDensity.current
    val swipeThreshold = with(density) { 88.dp.toPx() }
    val maxDrag = with(density) { 180.dp.toPx() }
    val railColor = patientCase.cardRailColor()
    var useShortName by rememberSaveable(patientCase.id) { mutableStateOf(false) }
    val displayName = if (useShortName) patientCase.compactDisplayName() else patientCase.patientName
    val dueLabel = patientCase.worklistDueLabel(selectedBucket = selectedBucket, expanded = expanded)

    Box(
        modifier = Modifier
            .fillMaxWidth()
            .pointerInput(patientCase.id) {
                detectTapGestures(onTap = { onToggle() })
            }
            .pointerInput(patientCase.id, patientCase.phoneNumber, patientCase.nextTaskId, swipeThreshold, maxDrag) {
                detectHorizontalDragGestures(
                    onDragCancel = { dragOffset = 0f },
                    onDragEnd = {
                        when {
                            dragOffset <= -swipeThreshold && patientCase.phoneNumber != null -> onCallPatient()
                            dragOffset >= swipeThreshold && patientCase.nextTaskId != null -> onCompleteTask()
                        }
                        dragOffset = 0f
                    },
                    onHorizontalDrag = { change, dragAmount ->
                        change.consume()
                        dragOffset = (dragOffset + dragAmount).coerceIn(-maxDrag, maxDrag)
                    },
                )
            },
    ) {
        SwipeActionBackground(
            dragOffset = dragOffset,
            canCall = patientCase.phoneNumber != null,
            canComplete = patientCase.nextTaskId != null,
        )
        Surface(
            modifier = Modifier
                .offset { IntOffset(dragOffset.roundToInt(), 0) },
            shape = RoundedCornerShape(HomeUiScale.CardRadius),
            color = MedtrackColors.Card,
            border = androidx.compose.foundation.BorderStroke(1.dp, MedtrackColors.Border.copy(alpha = 0.72f)),
        ) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(IntrinsicSize.Min),
            ) {
                Box(
                    modifier = Modifier
                        .width(HomeUiScale.CardRailWidth)
                        .fillMaxHeight()
                        .background(railColor),
                )
                Column(
                    modifier = Modifier.padding(
                        horizontal = HomeUiScale.CardHorizontalPadding,
                        vertical = if (expanded) HomeUiScale.CardExpandedVerticalPadding else HomeUiScale.CardVerticalPadding,
                    ),
                    verticalArrangement = Arrangement.spacedBy(
                        if (expanded) HomeUiScale.CardExpandedGap else HomeUiScale.CardCollapsedGap,
                    ),
                ) {
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(HomeUiScale.CardHeaderGap),
                        verticalAlignment = Alignment.Top,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        CategoryIcon(
                            color = patientCase.categoryColor(),
                            iconResId = patientCase.iconResId(),
                            modifier = Modifier.clickable(onClick = onCategoryFilter),
                        )
                        Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Row(
                                horizontalArrangement = Arrangement.spacedBy(6.dp),
                                verticalAlignment = Alignment.Top,
                                modifier = Modifier.fillMaxWidth(),
                            ) {
                                Column(
                                    modifier = Modifier.weight(1f),
                                    verticalArrangement = Arrangement.spacedBy(HomeUiScale.CardTextGap),
                                ) {
                                    Text(
                                        text = displayName,
                                        color = MedtrackColors.Ink,
                                        style = MaterialTheme.typography.titleSmall.copy(fontSize = HomeUiScale.CardNameText),
                                        fontWeight = FontWeight.Bold,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis,
                                        onTextLayout = { result ->
                                            if (result.hasVisualOverflow && !useShortName) {
                                                useShortName = true
                                            }
                                        },
                                    )
                                    Row(
                                        horizontalArrangement = Arrangement.spacedBy(7.dp),
                                        verticalAlignment = Alignment.CenterVertically,
                                        modifier = Modifier.fillMaxWidth(),
                                    ) {
                                        if (expanded) {
                                            CompactStatusPill(text = patientCase.categoryLabel, color = patientCase.categoryColor())
                                        }
                                        Text(
                                            text = patientCase.summaryLine(),
                                            color = MedtrackColors.Muted,
                                            style = MaterialTheme.typography.bodySmall.copy(fontSize = HomeUiScale.CardSummaryText),
                                            maxLines = 1,
                                            overflow = TextOverflow.Ellipsis,
                                            modifier = Modifier.weight(1f),
                                        )
                                    }
                                }
                                Column(
                                    horizontalAlignment = Alignment.End,
                                    verticalArrangement = Arrangement.spacedBy(5.dp),
                                ) {
                                    Row(
                                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                                        verticalAlignment = Alignment.CenterVertically,
                                    ) {
                                        patientCase.ageSexLine()?.let {
                                            Text(
                                                text = it,
                                                color = MedtrackColors.Muted,
                                                style = MaterialTheme.typography.labelMedium.copy(fontSize = HomeUiScale.CardMetaText),
                                                fontWeight = FontWeight.Bold,
                                                maxLines = 1,
                                                overflow = TextOverflow.Ellipsis,
                                            )
                                        }
                                        dueLabel?.let {
                                            DueChip(
                                                text = it,
                                                highRisk = patientCase.isHighRisk,
                                            )
                                        }
                                    }
                                    if (patientCase.isHighRisk) {
                                        RiskFlagIcon(onClick = onRiskClick)
                                    }
                                }
                            }
                            if (!patientCase.isHighRisk || (expanded && !patientCase.subcategoryLabel.isNullOrBlank())) {
                                FlowRow(
                                    horizontalArrangement = Arrangement.spacedBy(5.dp),
                                    verticalArrangement = Arrangement.spacedBy(3.dp),
                                ) {
                                    if (!patientCase.isHighRisk) {
                                        PatientStatePill(patientCase = patientCase, onRiskClick = onRiskClick)
                                    }
                                    if (expanded) {
                                        patientCase.subcategoryLabel
                                            ?.takeIf { it.isNotBlank() }
                                            ?.let { CompactStatusPill(text = it, color = MedtrackColors.Primary) }
                                    }
                                }
                            }
                        }
                    }

                    patientCase.latestVitalSummary?.takeIf { it.isNotBlank() }?.let {
                        VitalStrip(summary = it)
                    }

                    if (expanded) {
                        patientCase.caseMetaLine()?.let {
                            Text(
                                text = it,
                                color = MedtrackColors.Muted,
                                style = MaterialTheme.typography.labelMedium.copy(fontSize = HomeUiScale.CardMetaText),
                                fontWeight = FontWeight.SemiBold,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                            )
                        }
                        TaskChipRow(patientCase = patientCase)
                        Row(horizontalArrangement = Arrangement.spacedBy(7.dp), modifier = Modifier.fillMaxWidth()) {
                            PatientActionButton(
                                label = "Call",
                                icon = Icons.Outlined.Phone,
                                onClick = onCallPatient,
                                modifier = Modifier.weight(1.12f),
                                enabled = patientCase.phoneNumber != null,
                                containerColor = MedtrackColors.Success,
                                contentColor = Color.White,
                            )
                            PatientActionButton(
                                label = "WhatsApp",
                                icon = Icons.AutoMirrored.Outlined.Chat,
                                onClick = onMessagePatient,
                                modifier = Modifier.width(48.dp),
                                enabled = patientCase.phoneNumber != null,
                                containerColor = MedtrackColors.Success.copy(alpha = 0.14f),
                                contentColor = MedtrackColors.Success,
                                showLabel = false,
                            )
                            PatientActionButton(
                                label = "Done",
                                icon = Icons.Outlined.CheckCircle,
                                onClick = onCompleteTask,
                                modifier = Modifier.width(48.dp),
                                enabled = patientCase.nextTaskId != null,
                                containerColor = MedtrackColors.Surface,
                                contentColor = MedtrackColors.Ink,
                                showLabel = false,
                            )
                            PatientActionButton(
                                label = "Open case",
                                icon = Icons.AutoMirrored.Outlined.OpenInNew,
                                onClick = onOpenCase,
                                modifier = Modifier.weight(1.28f),
                                enabled = true,
                                containerColor = MedtrackColors.Ink,
                                contentColor = Color.White,
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun CompactStatusPill(
    text: String,
    color: Color,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(50),
        color = color.copy(alpha = 0.12f),
        border = androidx.compose.foundation.BorderStroke(1.dp, color.copy(alpha = 0.26f)),
    ) {
        Text(
            text = text,
            modifier = Modifier.padding(
                horizontal = HomeUiScale.StatusPillPaddingHorizontal,
                vertical = HomeUiScale.StatusPillPaddingVertical,
            ),
            color = color,
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.SemiBold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
private fun PatientStatePill(
    patientCase: PatientCase,
    onRiskClick: () -> Unit,
) {
    if (patientCase.isHighRisk) {
        RiskFlagIcon(onClick = onRiskClick)
        return
    }

    CompactStatusPill(
        text = patientCase.primaryStateLabel(),
        color = patientCase.primaryStateColor(),
    )
}

@Composable
private fun RiskFlagIcon(onClick: () -> Unit) {
    Surface(
        modifier = Modifier
            .size(HomeUiScale.RiskFlagSize)
            .clickable(onClick = onClick),
        shape = RoundedCornerShape(50),
        color = MedtrackColors.Danger.copy(alpha = 0.1f),
        border = androidx.compose.foundation.BorderStroke(1.dp, MedtrackColors.Danger.copy(alpha = 0.24f)),
    ) {
        Box(contentAlignment = Alignment.Center) {
            Icon(
                imageVector = Icons.Outlined.Flag,
                contentDescription = "Red flag",
                tint = MedtrackColors.Danger,
                modifier = Modifier.size(HomeUiScale.RiskFlagIconSize),
            )
        }
    }
}

@Composable
private fun DueChip(text: String, highRisk: Boolean) {
    val color = if (highRisk) MedtrackColors.Danger else MedtrackColors.Muted
    Surface(
        shape = RoundedCornerShape(9.dp),
        color = color.copy(alpha = 0.08f),
        border = androidx.compose.foundation.BorderStroke(1.dp, color.copy(alpha = 0.14f)),
    ) {
        Text(
            text = text,
            color = color,
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(
                horizontal = HomeUiScale.DuePillPaddingHorizontal,
                vertical = HomeUiScale.DuePillPaddingVertical,
            ),
            maxLines = 1,
            softWrap = false,
        )
    }
}

private fun String.compactDueLabel(): String {
    val value = trim()
    Regex("""^\d{4}-\d{2}-\d{2}[T ](\d{2}:\d{2})""")
        .find(value)
        ?.groupValues
        ?.getOrNull(1)
        ?.let { return it }

    return runCatching {
        val parsed = SimpleDateFormat("yyyy-MM-dd", Locale.US).parse(value)
        parsed?.let {
            SimpleDateFormat("dd MMM", Locale.getDefault())
                .format(it)
                .uppercase(Locale.getDefault())
        }
    }.getOrNull() ?: value
}

@Composable
private fun VitalStrip(summary: String) {
    val metrics = summary.split("|").map { it.trim() }.filter { it.isNotBlank() }.take(4)
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(9.dp),
        color = MedtrackColors.Surface,
    ) {
        Row(
            modifier = Modifier.padding(
                horizontal = HomeUiScale.VitalPaddingHorizontal,
                vertical = HomeUiScale.VitalPaddingVertical,
            ),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            metrics.forEachIndexed { index, metric ->
                val parts = metric.split(Regex("\\s+"), limit = 2)
                VitalMetric(
                    label = parts.firstOrNull().orEmpty(),
                    value = parts.getOrNull(1).orEmpty(),
                    modifier = Modifier.weight(1f),
                )
                if (index < metrics.lastIndex) {
                    Box(
                        modifier = Modifier
                            .width(1.dp)
                            .height(22.dp)
                            .background(MedtrackColors.Border.copy(alpha = 0.55f)),
                    )
                }
            }
        }
    }
}

@Composable
private fun VitalMetric(label: String, value: String, modifier: Modifier = Modifier) {
    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(1.dp)) {
        Text(
            text = label.uppercase(Locale.getDefault()),
            color = MedtrackColors.Muted,
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
        )
        Text(
            text = value,
            color = MedtrackColors.Ink,
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun TaskChipRow(patientCase: PatientCase) {
    val chips = listOfNotNull(patientCase.nextTaskTitle?.takeIf { it.isNotBlank() })
        .ifEmpty { listOf("No open task") }
    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
        Text(
            text = "TASKS \u2022 ${if (patientCase.nextTaskTitle.isNullOrBlank()) 0 else 1}",
            color = MedtrackColors.Muted,
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Bold,
        )
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            chips.forEach { label ->
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = MedtrackColors.Surface,
                    border = androidx.compose.foundation.BorderStroke(1.dp, MedtrackColors.Border.copy(alpha = 0.62f)),
                ) {
                    Text(
                        text = label,
                        color = MedtrackColors.Ink,
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(
                            horizontal = HomeUiScale.TaskChipPaddingHorizontal,
                            vertical = HomeUiScale.TaskChipPaddingVertical,
                        ),
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }
    }
}

@Composable
private fun PatientActionButton(
    label: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    onClick: () -> Unit,
    enabled: Boolean,
    containerColor: Color,
    contentColor: Color,
    modifier: Modifier = Modifier,
    showLabel: Boolean = true,
) {
    Button(
        onClick = onClick,
        modifier = modifier.height(HomeUiScale.ActionButtonHeight),
        enabled = enabled,
        colors = ButtonDefaults.buttonColors(
            containerColor = containerColor,
            contentColor = contentColor,
            disabledContainerColor = MedtrackColors.Surface,
            disabledContentColor = MedtrackColors.Muted,
        ),
        contentPadding = PaddingValues(horizontal = 6.dp, vertical = 6.dp),
    ) {
        Icon(
            imageVector = icon,
            contentDescription = if (showLabel) null else label,
            modifier = Modifier.size(HomeUiScale.ActionIconSize),
        )
        if (showLabel) {
            Spacer(modifier = Modifier.width(5.dp))
            Text(
                text = label,
                maxLines = 1,
                softWrap = false,
                overflow = TextOverflow.Clip,
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

@Composable
private fun BoxScope.SwipeActionBackground(
    dragOffset: Float,
    canCall: Boolean,
    canComplete: Boolean,
) {
    val isCall = dragOffset < 0f
    val isActive = dragOffset != 0f
    if (!isActive) return

    val enabled = if (isCall) canCall else canComplete
    val color = when {
        !enabled -> MedtrackColors.Muted.copy(alpha = 0.36f)
        isCall -> MedtrackColors.Success
        else -> Color(0xFF24313B)
    }
    val alignment = if (isCall) Alignment.CenterEnd else Alignment.CenterStart
    val label = if (isCall) "Call" else "Done"

    Box(
        modifier = Modifier
            .matchParentSize()
            .background(color = color, shape = RoundedCornerShape(HomeUiScale.CardRadius))
            .padding(horizontal = 18.dp),
        contentAlignment = alignment,
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(
                imageVector = if (isCall) Icons.Outlined.Phone else Icons.Outlined.CheckCircle,
                contentDescription = null,
                tint = Color.White,
                modifier = Modifier.size(19.dp),
            )
            Text(text = label, color = Color.White, fontWeight = FontWeight.SemiBold)
        }
    }
}

@Composable
private fun CategoryIcon(color: Color, iconResId: Int, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier.size(HomeUiScale.CategoryIconSize),
        shape = RoundedCornerShape(HomeUiScale.CategoryIconRadius),
        color = color.copy(alpha = 0.13f),
    ) {
        Row(horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
            Icon(
                painter = painterResource(iconResId),
                contentDescription = null,
                tint = color,
                modifier = Modifier.size(HomeUiScale.CategoryGlyphSize),
            )
        }
    }
}

private fun PatientCase.demographicsLine(): String =
    listOfNotNull(
        uhid,
        age?.let { "${it}y" },
        sexLabel,
        place,
    ).joinToString(" \u2022 ")

private fun PatientCase.ageSexLine(): String? =
    listOfNotNull(
        sexLabel
            ?.trim()
            ?.takeIf { it.isNotBlank() }
            ?.let { if (it.length == 1) it.uppercase(Locale.getDefault()) else it.first().uppercaseChar().toString() },
        age?.let { it.toString() },
    ).joinToString(" \u00B7 ").takeIf { it.isNotBlank() }

private fun PatientCase.caseMetaLine(): String? =
    listOfNotNull(
        uhid.takeIf { it.isNotBlank() },
        place?.takeIf { it.isNotBlank() },
    ).joinToString(" \u2022 ").takeIf { it.isNotBlank() }

private fun PatientCase.summaryLine(): String =
    diagnosis.takeIf { it.isNotBlank() } ?: categoryLabel

private fun PatientCase.compactDisplayName(): String {
    val parts = patientName.trim().split(Regex("\\s+")).filter { it.isNotBlank() }
    if (parts.size < 2) return patientName
    val last = parts.last()
    val abbreviatedLast = last.firstOrNull()?.uppercaseChar()?.let { "$it." } ?: last
    return (parts.dropLast(1) + abbreviatedLast).joinToString(" ")
}

private fun PatientCase.worklistDueLabel(selectedBucket: String?, expanded: Boolean): String? {
    val dueDate = nextTaskDueDate?.takeIf { it.isNotBlank() } ?: return null
    val compact = dueDate.compactDueLabel()
    if (expanded) return compact

    return when (selectedBucket) {
        "overdue" -> "Due $compact"
        else -> null
    }
}

private fun PatientCase.primaryStateLabel(): String =
    if (isHighRisk) "RED FLAG" else status.label.uppercase(Locale.getDefault())

private fun PatientCase.primaryStateColor(): Color =
    if (isHighRisk) {
        MedtrackColors.Danger
    } else {
        when (status) {
            CaseStatus.ACTIVE -> MedtrackColors.Success
            CaseStatus.COMPLETED -> MedtrackColors.Primary
            CaseStatus.CANCELLED,
            CaseStatus.LOSS_TO_FOLLOW_UP -> MedtrackColors.Muted
        }
    }

private fun PatientCase.cardRailColor(): Color =
    if (isHighRisk) MedtrackColors.Danger else categoryColor()

private fun PatientCase.categoryColor(): Color =
    if (categoryLabel.isCustomRehabLabel()) MedtrackColors.CustomRehab else category.color()

private fun CaseCategory.color(): Color =
    when (this) {
        CaseCategory.ANC -> MedtrackColors.Anc
        CaseCategory.SURGERY -> MedtrackColors.Surgery
        CaseCategory.MEDICINE -> MedtrackColors.Medicine
        CaseCategory.OTHER -> MedtrackColors.Primary
    }

private fun PatientCase.riskReasonSource(): String =
    if (category == CaseCategory.ANC) "from ANC reason set" else "manually flagged"

private fun String.isCustomRehabLabel(): Boolean =
    trim().replace("-", " ").contains("rehab", ignoreCase = true)

private fun PatientCase.iconResId(): Int =
    subcategoryValue?.let { subcategoryIconResId(it) } ?: category.iconResId()

private fun CaseCategory.iconResId(): Int =
    when (this) {
        CaseCategory.ANC -> DesignR.drawable.ic_cat_anc
        CaseCategory.SURGERY -> DesignR.drawable.ic_cat_surgery
        CaseCategory.MEDICINE -> DesignR.drawable.ic_cat_medicine
        CaseCategory.OTHER -> DesignR.drawable.ic_cat_medicine
    }

private fun subcategoryIconResId(value: String): Int? =
    when (value.uppercase()) {
        "GENERAL_SURGERY" -> DesignR.drawable.ic_sub_general_surgery
        "ORTHOPEDICS" -> DesignR.drawable.ic_sub_orthopedics
        "PLASTIC_SURGERY" -> DesignR.drawable.ic_sub_plastic_surgery
        "PEDIATRIC_SURGERY" -> DesignR.drawable.ic_sub_pediatric_surgery
        "UROLOGY" -> DesignR.drawable.ic_sub_urology
        "ENT" -> DesignR.drawable.ic_sub_ent
        "OTHER_SPECIALTY" -> DesignR.drawable.ic_sub_other_specialty
        "GENERAL_MEDICINE" -> DesignR.drawable.ic_sub_general_medicine
        "PSYCHIATRY" -> DesignR.drawable.ic_sub_psychiatry
        "CARDIOLOGY_ECHO" -> DesignR.drawable.ic_sub_cardiology_echo
        "PEDIATRIC" -> DesignR.drawable.ic_sub_pediatric
        "MEDICAL_ONCOLOGY" -> DesignR.drawable.ic_sub_medical_oncology
        else -> null
    }

private fun List<String>.toggle(value: String): List<String> =
    if (value in this) filterNot { it == value } else this + value
