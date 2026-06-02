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
import androidx.compose.material.icons.outlined.Event
import androidx.compose.material.icons.outlined.Flag
import androidx.compose.material.icons.outlined.ExpandMore
import androidx.compose.material.icons.outlined.Phone
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.Tune
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
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.naveenhospital.medtrack.core.designsystem.R as DesignR
import com.naveenhospital.medtrack.core.designsystem.MedtrackColors
import com.naveenhospital.medtrack.core.designsystem.MedtrackCategoryTile
import com.naveenhospital.medtrack.core.designsystem.MedtrackDuePill
import com.naveenhospital.medtrack.core.designsystem.MedtrackDueTone
import com.naveenhospital.medtrack.core.designsystem.MedtrackPullRefreshBox
import com.naveenhospital.medtrack.core.designsystem.MedtrackRadius
import com.naveenhospital.medtrack.core.designsystem.MedtrackRiskFlag
import com.naveenhospital.medtrack.core.designsystem.MedtrackStatusPill
import com.naveenhospital.medtrack.core.designsystem.medtrackShortDateLabel
import com.naveenhospital.medtrack.core.domain.model.CaseCategory
import com.naveenhospital.medtrack.core.domain.model.CaseStatus
import com.naveenhospital.medtrack.core.domain.model.CategoryFilterOption
import com.naveenhospital.medtrack.core.domain.model.InboxStats
import com.naveenhospital.medtrack.core.domain.model.PatientCase
import com.naveenhospital.medtrack.core.domain.model.SubcategoryFilterOption
import com.naveenhospital.medtrack.core.domain.model.VitalsThresholdConfig
import androidx.paging.compose.LazyPagingItems
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.roundToInt

private object HomeUiScale {
    val ScreenHorizontalPadding = 18.dp
    val ScreenVerticalPadding = 4.dp
    val SectionGap = 10.dp
    val ListCardGap = 8.dp
    val ListBottomPadding = 104.dp

    val HeaderAvatarSize = 44.dp
    val HeaderButtonSize = 40.dp
    val HeaderButtonRadius = 13.dp
    val HeaderIconSize = 18.dp
    val HeaderDotSize = 7.dp
    val HeaderDateText = 11.5.sp
    val HeaderGreetingText = 20.sp

    val SearchHeight = 44.dp
    val SearchRadius = 14.dp
    val SearchHorizontalPaddingStart = 14.dp
    val SearchHorizontalPaddingEnd = 14.dp
    val SearchGap = 10.dp
    val SearchIconSize = 20.dp
    val SearchFilterButtonSize = 28.dp
    val SearchFilterButtonRadius = 10.dp
    val SearchText = 15.sp

    val BucketGap = 8.dp
    val BucketHeight = 37.dp
    val BucketHorizontalPadding = 12.dp
    val BucketInnerGap = 7.dp
    val BucketText = 12.sp
    val BucketCountPaddingHorizontal = 6.dp
    val BucketCountPaddingVertical = 2.dp

    val CardRadius = 16.dp
    val CardRailWidth = 4.dp
    val CardHorizontalPadding = 13.dp
    val CardVerticalPadding = 13.dp
    val CardExpandedVerticalPadding = 10.dp
    val CardCollapsedGap = 6.dp
    val CardExpandedGap = 8.dp
    val CardHeaderGap = 12.dp
    val CardTextGap = 4.dp
    val CardNameText = 16.sp
    val CardSummaryText = 13.5.sp
    val CardMetaText = 12.5.sp

    val CategoryIconSize = 44.dp
    val CategoryIconRadius = 12.dp
    val CategoryGlyphSize = 24.dp
    val StatusPillPaddingHorizontal = 8.dp
    val StatusPillPaddingVertical = 2.dp
    val DuePillPaddingHorizontal = 6.dp
    val DuePillPaddingVertical = 2.dp
    val RiskFlagSize = 24.dp
    val RiskFlagIconSize = 17.dp

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
    vitalsThresholds: VitalsThresholdConfig?,
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
                        vitalsThresholds = vitalsThresholds,
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
            onCallPatient = { onCallPatient(patientCase) },
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
                fontWeight = FontWeight.ExtraBold,
            )
            Text(
                text = "Hi $greetingName.",
                color = MedtrackColors.Ink,
                style = MaterialTheme.typography.titleMedium.copy(fontSize = HomeUiScale.HeaderGreetingText),
                fontWeight = FontWeight.ExtraBold,
            )
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
            Box(
                modifier = Modifier
                    .size(HomeUiScale.SearchFilterButtonSize)
                    .clickable(onClick = onFilterClick),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    imageVector = Icons.Outlined.Tune,
                    contentDescription = "Filters",
                    tint = MedtrackColors.Ink,
                    modifier = Modifier.size(HomeUiScale.SearchIconSize),
                )
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
        Surface(
            shape = RoundedCornerShape(50),
            color = MedtrackColors.Card,
            border = androidx.compose.foundation.BorderStroke(1.dp, MedtrackColors.Border.copy(alpha = 0.78f)),
        ) {
            Row(
                modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp),
                horizontalArrangement = Arrangement.spacedBy(4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "By time",
                    style = MaterialTheme.typography.labelSmall.copy(fontSize = 13.sp),
                    color = MedtrackColors.InkSoft,
                    fontWeight = FontWeight.Bold,
                )
                Icon(
                    imageVector = Icons.Outlined.ExpandMore,
                    contentDescription = null,
                    tint = MedtrackColors.InkSoft,
                    modifier = Modifier.size(16.dp),
                )
            }
        }
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
    onCallPatient: () -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(
        sheetState = sheetState,
        onDismissRequest = onDismiss,
        containerColor = Color.White,
    ) {
        val reasons = patientCase.highRiskReasons.ifEmpty { listOf("Server marked this case as red.") }
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(start = 16.dp, end = 16.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top,
            ) {
                Row(
                    modifier = Modifier.weight(1f),
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Surface(
                        shape = RoundedCornerShape(12.dp),
                        color = MedtrackColors.Danger.copy(alpha = 0.08f),
                        modifier = Modifier.size(38.dp),
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Icon(imageVector = Icons.Outlined.Flag, contentDescription = null, tint = MedtrackColors.Danger, modifier = Modifier.size(21.dp))
                        }
                    }
                    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(
                            text = "Why flagged",
                            color = MedtrackColors.Ink,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            text = "${patientCase.patientName} · ${reasons.size} ${if (reasons.size == 1) "risk reason" else "risk reasons"}",
                            color = MedtrackColors.InkSoft,
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.SemiBold,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                }
            }
            Text(
                text = patientCase.riskReasonSource().uppercase(),
                color = if (patientCase.category == CaseCategory.ANC) MedtrackColors.Anc else MedtrackColors.Warning,
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.ExtraBold,
            )
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(14.dp),
                color = Color.White,
                border = androidx.compose.foundation.BorderStroke(1.dp, MedtrackColors.Border.copy(alpha = 0.72f)),
            ) {
                Column(modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp)) {
                    reasons.forEach { reason ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 10.dp),
                            horizontalArrangement = Arrangement.spacedBy(9.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Box(
                                modifier = Modifier
                                    .size(7.dp)
                                    .background(MedtrackColors.Danger, RoundedCornerShape(50)),
                            )
                            Text(
                                text = reason,
                                color = MedtrackColors.Ink,
                                style = MaterialTheme.typography.bodyMedium,
                                fontWeight = FontWeight.SemiBold,
                                modifier = Modifier.weight(1f),
                            )
                            MedtrackStatusPill(text = "High", color = MedtrackColors.Danger)
                        }
                    }
                }
            }
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Surface(
                    modifier = Modifier
                        .weight(0.75f)
                        .height(46.dp)
                        .clickable(onClick = onDismiss),
                    shape = RoundedCornerShape(12.dp),
                    color = Color.White,
                    border = androidx.compose.foundation.BorderStroke(1.dp, MedtrackColors.Border),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text("Close", color = MedtrackColors.Ink, fontWeight = FontWeight.SemiBold)
                    }
                }
                Button(
                    onClick = onCallPatient,
                    enabled = !patientCase.phoneNumber.isNullOrBlank(),
                    modifier = Modifier
                        .weight(1.6f)
                        .height(46.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = MedtrackColors.Success),
                ) {
                    Icon(imageVector = Icons.Outlined.Phone, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(5.dp))
                    Text("Call patient")
                }
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

    ModalBottomSheet(
        sheetState = sheetState,
        onDismissRequest = onDismiss,
        containerColor = Color.White,
    ) {
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
    option.category.color()

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun BucketChips(
    stats: InboxStats,
    selectedBucket: String?,
    onBucketSelected: (String?) -> Unit,
) {
    Box(modifier = Modifier.fillMaxWidth()) {
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
            Spacer(modifier = Modifier.width(34.dp))
        }
        Box(
            modifier = Modifier
                .align(Alignment.CenterEnd)
                .width(34.dp)
                .height(HomeUiScale.BucketHeight)
                .background(
                    Brush.horizontalGradient(
                        listOf(Color.Transparent, MedtrackColors.Surface),
                    ),
                ),
        )
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
        shape = MedtrackRadius.PillShape,
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
    vitalsThresholds: VitalsThresholdConfig?,
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
    val swipeThreshold = with(density) { 40.dp.toPx() }
    val maxDrag = with(density) { 96.dp.toPx() }
    val railColor = patientCase.cardRailColor()
    val displayName = patientCase.patientName
    val dueLabel = patientCase.worklistDueLabel(selectedBucket = selectedBucket, expanded = expanded)

    Box(
        modifier = Modifier
            .fillMaxWidth()
            .pointerInput(patientCase.id) {
                detectTapGestures(
                    onTap = {
                        if (dragOffset != 0f) {
                            dragOffset = 0f
                        } else {
                            onToggle()
                        }
                    },
                )
            }
            .pointerInput(patientCase.id, patientCase.phoneNumber, patientCase.nextTaskId, swipeThreshold, maxDrag) {
                detectHorizontalDragGestures(
                    onDragCancel = { dragOffset = 0f },
                    onDragEnd = {
                        dragOffset = when {
                            dragOffset <= -swipeThreshold && patientCase.phoneNumber != null -> -maxDrag
                            dragOffset >= swipeThreshold && patientCase.nextTaskId != null -> maxDrag
                            else -> 0f
                        }
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
            onCallPatient = {
                dragOffset = 0f
                onCallPatient()
            },
            onCompleteTask = {
                dragOffset = 0f
                onCompleteTask()
            },
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
                                        fontWeight = FontWeight.ExtraBold,
                                        maxLines = 2,
                                        overflow = TextOverflow.Ellipsis,
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
                                            fontWeight = FontWeight.SemiBold,
                                            maxLines = 2,
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
                                                highRisk = false,
                                            )
                                        }
                                    }
                                    if (patientCase.isHighRisk) {
                                        RiskFlagIcon(count = patientCase.riskReasonCount(), onClick = onRiskClick)
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

                    if (expanded) {
                        patientCase.latestVitalSummary?.takeIf { it.isNotBlank() }?.let {
                            VitalStrip(summary = it, thresholds = vitalsThresholds)
                        }
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
private fun RiskReasonsInlineChip(
    patientCase: PatientCase,
    onClick: () -> Unit,
) {
    val count = patientCase.highRiskReasons.count { it.isNotBlank() }.takeIf { it > 0 } ?: 1
    val reason = if (count == 1) "1 risk reason" else "$count risk reasons"
    Surface(
        modifier = Modifier.clickable(onClick = onClick),
        shape = RoundedCornerShape(13.dp),
        color = MedtrackColors.Danger.copy(alpha = 0.08f),
        border = androidx.compose.foundation.BorderStroke(1.dp, MedtrackColors.Danger.copy(alpha = 0.18f)),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 7.dp),
            horizontalArrangement = Arrangement.spacedBy(7.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                imageVector = Icons.Outlined.Flag,
                contentDescription = null,
                tint = MedtrackColors.Danger,
                modifier = Modifier.size(15.dp),
            )
            Text(
                text = reason,
                color = MedtrackColors.Danger,
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.ExtraBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f),
            )
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
        RiskFlagIcon(count = patientCase.riskReasonCount(), onClick = onRiskClick)
        return
    }

    CompactStatusPill(
        text = patientCase.primaryStateLabel(),
        color = patientCase.primaryStateColor(),
    )
}

@Composable
private fun RiskFlagIcon(count: Int?, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .height(HomeUiScale.RiskFlagSize)
            .clickable(onClick = onClick),
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            imageVector = Icons.Outlined.Flag,
            contentDescription = "Red flag",
            tint = MedtrackColors.Danger,
            modifier = Modifier.size(HomeUiScale.RiskFlagIconSize),
        )
        count?.let {
            Text(
                text = it.coerceAtLeast(1).toString(),
                color = MedtrackColors.Danger,
                style = MaterialTheme.typography.labelMedium.copy(fontSize = 13.5.sp),
                fontWeight = FontWeight.ExtraBold,
                maxLines = 1,
            )
        }
    }
}

@Composable
private fun DueChip(text: String, highRisk: Boolean) {
    val tone = when {
        highRisk || text.contains("overdue", ignoreCase = true) -> MedtrackDueTone.Overdue
        text.contains("today", ignoreCase = true) -> MedtrackDueTone.Today
        text.contains("await", ignoreCase = true) -> MedtrackDueTone.Awaiting
        else -> MedtrackDueTone.Upcoming
    }
    MedtrackDuePill(text = text, tone = tone)
}

private fun String.compactDueLabel(): String {
    val value = trim()
    return medtrackShortDateLabel(value) ?: value
}

@Composable
private fun VitalStrip(summary: String, thresholds: VitalsThresholdConfig?) {
    val metrics = summary.toVitalMetrics(thresholds)
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        color = MedtrackColors.SurfaceAlt.copy(alpha = 0.72f),
        border = androidx.compose.foundation.BorderStroke(1.dp, MedtrackColors.Border.copy(alpha = 0.7f)),
    ) {
        Row(
            modifier = Modifier.padding(
                horizontal = 6.dp,
                vertical = 6.dp,
            ),
            horizontalArrangement = Arrangement.spacedBy(5.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            metrics.forEach { metric ->
                VitalMetric(
                    metric = metric,
                    modifier = Modifier.weight(1f),
                )
            }
        }
    }
}

@Composable
private fun VitalMetric(metric: VitalMetricDisplay, modifier: Modifier = Modifier) {
    val color = metric.status.vitalStatusColor()
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(10.dp),
        color = color.copy(alpha = if (metric.status == "na") 0.08f else 0.13f),
        border = androidx.compose.foundation.BorderStroke(1.dp, color.copy(alpha = if (metric.status == "na") 0.12f else 0.24f)),
    ) {
        Column(
            modifier = Modifier.padding(horizontal = HomeUiScale.VitalPaddingHorizontal, vertical = HomeUiScale.VitalPaddingVertical),
            verticalArrangement = Arrangement.spacedBy(1.dp),
        ) {
            Text(
                text = metric.label.uppercase(Locale.getDefault()),
                color = MedtrackColors.Muted,
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.Bold,
                maxLines = 1,
            )
            Text(
                text = metric.value,
                color = color,
                style = MaterialTheme.typography.titleSmall.copy(fontSize = 14.sp),
                fontWeight = FontWeight.ExtraBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (metric.unit.isNotBlank()) {
                Text(
                    text = metric.unit,
                    color = MedtrackColors.Muted,
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

private data class VitalMetricDisplay(
    val label: String,
    val value: String,
    val unit: String,
    val status: String,
)

private fun String.toVitalMetrics(thresholds: VitalsThresholdConfig?): List<VitalMetricDisplay> {
    val values = split("|")
        .map { it.trim() }
        .filter { it.isNotBlank() }
        .mapNotNull { metric ->
            val parts = metric.split(Regex("\\s+"), limit = 2)
            val label = parts.firstOrNull().orEmpty().normalizedVitalKey()
            val value = parts.getOrNull(1).orEmpty()
            label.takeIf { it.isNotBlank() }?.let { it to value }
        }
        .toMap()

    fun metric(label: String, key: String, unit: String): VitalMetricDisplay {
        val value = values[key]?.takeIf { it.isNotBlank() } ?: "\u2014"
        val status = if (value == "\u2014") "na" else key.vitalStatusFor(value, thresholds)
        return VitalMetricDisplay(label = label, value = value, unit = unit, status = status)
    }

    return listOf(
        metric("BP", "bp", "mmHg"),
        metric("Pulse", "pulse", "bpm"),
        metric("SpO2", "spo2", "%"),
        metric("Hb", "hemoglobin", "g/dL"),
    )
}

private fun String.normalizedVitalKey(): String {
    val normalized = trim().lowercase(Locale.US).replace(" ", "")
    return when {
        normalized == "bp" || normalized.contains("bloodpressure") -> "bp"
        normalized == "pr" || normalized == "pulse" -> "pulse"
        normalized.startsWith("spo") -> "spo2"
        normalized == "hb" || normalized == "hgb" || normalized.contains("hemoglobin") -> "hemoglobin"
        else -> ""
    }
}

private fun String.vitalStatusFor(value: String, thresholds: VitalsThresholdConfig?): String {
    val normalized = trim().lowercase(Locale.US).replace(" ", "")
    return when (normalized) {
        "bp" -> {
            val parts = value.split("/")
            val systolic = parts.getOrNull(0)?.filter(Char::isDigit)?.toIntOrNull()
            val diastolic = parts.getOrNull(1)?.filter(Char::isDigit)?.toIntOrNull()
            thresholds?.evaluateBloodPressure(systolic, diastolic)?.status
                ?: fallbackBloodPressureStatus(systolic, diastolic)
        }
        "pr", "pulse" -> {
            val number = value.extractNumericValue()
            thresholds?.evaluateMetric("pr", number)?.status ?: fallbackPulseStatus(number)
        }
        "spo2", "spo₂" -> {
            val number = value.extractNumericValue()
            thresholds?.evaluateMetric("spo2", number)?.status ?: fallbackSpo2Status(number)
        }
        "hb", "hgb", "hemoglobin" -> {
            val number = value.extractNumericValue()
            thresholds?.evaluateMetric("hemoglobin", number)?.status ?: fallbackHemoglobinStatus(number)
        }
        else -> "na"
    }
}

private fun String.extractNumericValue(): Double? =
    Regex("""-?\d+(\.\d+)?""").find(this)?.value?.toDoubleOrNull()

private fun fallbackBloodPressureStatus(systolic: Int?, diastolic: Int?): String =
    when {
        systolic == null && diastolic == null -> "na"
        systolic != null && systolic >= 140 || diastolic != null && diastolic >= 90 -> "red"
        systolic != null && systolic >= 120 || diastolic != null && diastolic >= 80 -> "orange"
        else -> "green"
    }

private fun fallbackPulseStatus(value: Double?): String =
    when {
        value == null -> "na"
        value < 50.0 || value > 110.0 -> "red"
        value < 60.0 || value > 100.0 -> "orange"
        else -> "green"
    }

private fun fallbackSpo2Status(value: Double?): String =
    when {
        value == null -> "na"
        value < 92.0 -> "red"
        value < 96.0 -> "orange"
        else -> "green"
    }

private fun fallbackHemoglobinStatus(value: Double?): String =
    when {
        value == null -> "na"
        value < 10.0 -> "red"
        value < 11.0 -> "orange"
        else -> "green"
    }

private fun String.vitalStatusColor(): Color =
    when (this) {
        "green" -> MedtrackColors.Success
        "orange" -> MedtrackColors.Warning
        "red" -> MedtrackColors.Danger
        "neutral" -> MedtrackColors.Primary
        else -> MedtrackColors.Muted
    }

@Composable
@OptIn(ExperimentalLayoutApi::class)
private fun TaskChipRow(patientCase: PatientCase) {
    val taskTitle = patientCase.nextTaskTitle?.takeIf { it.isNotBlank() }
    Surface(
        shape = RoundedCornerShape(13.dp),
        color = MedtrackColors.Surface,
        border = androidx.compose.foundation.BorderStroke(1.dp, MedtrackColors.Border.copy(alpha = 0.68f)),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                imageVector = Icons.Outlined.Event,
                contentDescription = null,
                tint = if (taskTitle == null) MedtrackColors.Muted else MedtrackColors.Primary,
                modifier = Modifier.size(17.dp),
            )
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(1.dp)) {
                Text(
                    text = if (taskTitle == null) "0 open tasks" else "1 open task",
                    color = MedtrackColors.Muted,
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.ExtraBold,
                    maxLines = 1,
                )
                Text(
                    text = taskTitle ?: "No open task",
                    color = if (taskTitle == null) MedtrackColors.Muted else MedtrackColors.Ink,
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
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
    onCallPatient: () -> Unit,
    onCompleteTask: () -> Unit,
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
    val action = if (isCall) onCallPatient else onCompleteTask

    Box(
        modifier = Modifier
            .matchParentSize()
            .background(MedtrackColors.SurfaceAlt, shape = RoundedCornerShape(HomeUiScale.CardRadius))
            .padding(horizontal = 8.dp, vertical = 7.dp),
        contentAlignment = alignment,
    ) {
        Surface(
            modifier = Modifier
                .width(80.dp)
                .height(88.dp)
                .clickable(enabled = enabled, onClick = action),
            shape = RoundedCornerShape(16.dp),
            color = color,
            shadowElevation = if (enabled) 2.dp else 0.dp,
        ) {
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center,
            ) {
                Icon(
                    imageVector = if (isCall) Icons.Outlined.Phone else Icons.Outlined.CheckCircle,
                    contentDescription = label,
                    tint = Color.White,
                    modifier = Modifier.size(19.dp),
                )
                Text(text = label, color = Color.White, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall)
            }
        }
    }
}

@Composable
private fun CategoryIcon(color: Color, iconResId: Int, modifier: Modifier = Modifier) {
    MedtrackCategoryTile(
        iconResId = iconResId,
        tint = color,
        modifier = modifier,
        size = HomeUiScale.CategoryIconSize,
        radius = HomeUiScale.CategoryIconRadius,
    )
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

private fun PatientCase.riskReasonCount(): Int =
    highRiskReasons.count { it.isNotBlank() }.coerceAtLeast(1)

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
    category.color()

private fun CaseCategory.color(): Color =
    when (this) {
        CaseCategory.ANC -> MedtrackColors.Anc
        CaseCategory.SURGERY -> MedtrackColors.Surgery
        CaseCategory.MEDICINE -> MedtrackColors.Medicine
        CaseCategory.OTHER -> MedtrackColors.Primary
    }

private fun PatientCase.riskReasonSource(): String =
    if (category == CaseCategory.ANC) "from ANC reason set" else "manually flagged"

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
