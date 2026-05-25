package com.naveenhospital.medtrack

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import androidx.compose.runtime.DisposableEffect
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.Folder
import androidx.compose.material.icons.outlined.HealthAndSafety
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Logout
import androidx.compose.material.icons.outlined.Person
import androidx.compose.material.icons.outlined.Phone
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.Sync
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarResult
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.paging.LoadState
import androidx.paging.compose.collectAsLazyPagingItems
import com.naveenhospital.medtrack.core.designsystem.MedtrackColors
import com.naveenhospital.medtrack.core.designsystem.MedtrackCompactCard
import com.naveenhospital.medtrack.core.designsystem.MedtrackIconBadge
import com.naveenhospital.medtrack.core.designsystem.MedtrackMiniPill
import com.naveenhospital.medtrack.core.designsystem.MedtrackTheme
import com.naveenhospital.medtrack.core.designsystem.MedtrackPage
import com.naveenhospital.medtrack.core.designsystem.MedtrackSectionTitle
import com.naveenhospital.medtrack.core.domain.model.PatientCase
import com.naveenhospital.medtrack.core.domain.model.CaseCategory
import com.naveenhospital.medtrack.core.network.model.UserProfileDto
import com.naveenhospital.medtrack.feature.auth.LockSetupScreen
import com.naveenhospital.medtrack.feature.auth.LoginScreen
import com.naveenhospital.medtrack.feature.auth.UnlockScreen
import com.naveenhospital.medtrack.feature.calls.CallOutcomeSheet
import com.naveenhospital.medtrack.feature.calls.CallsScreen
import com.naveenhospital.medtrack.feature.cases.CaseDetailScreen
import com.naveenhospital.medtrack.feature.cases.CaseListScreen
import com.naveenhospital.medtrack.feature.cases.VitalsEntryInput
import com.naveenhospital.medtrack.feature.home.HomeScreen
import com.naveenhospital.medtrack.feature.notifications.NotificationsScreen
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private const val IDLE_RELOCK_MILLIS = 15 * 60 * 1000L

private object Routes {
    const val LOGIN = "login"
    const val LOCK_SETUP = "lock_setup"
    const val UNLOCK = "unlock"
    const val HOME = "home"
    const val CASES = "cases"
    const val CASE_DETAIL = "cases/{caseId}"
    const val CALLS = "calls"
    const val NOTIFICATIONS = "notifications"
    const val ME = "me"

    fun caseDetail(caseId: String): String = "cases/$caseId"
}

private data class BottomDestination(
    val route: String,
    val label: String,
    val icon: ImageVector,
)

private val bottomDestinations = listOf(
    BottomDestination(Routes.HOME, "Home", Icons.Outlined.Home),
    BottomDestination(Routes.CASES, "Cases", Icons.Outlined.Folder),
    BottomDestination(Routes.CALLS, "Calls", Icons.Outlined.Phone),
    BottomDestination(Routes.ME, "Me", Icons.Outlined.Person),
)

private object BottomNavScale {
    val ShellHeight = 88.dp
    val BarHeight = 74.dp
    val BarHorizontalPadding = 18.dp
    val CenterSpacerWidth = 72.dp
    val CenterButtonSize = 56.dp
    val CenterButtonRadius = 18.dp
    val CenterButtonYOffset = 8.dp
    val CenterIconSize = 29.dp
    val ItemPaddingTop = 8.dp
    val ItemPaddingBottom = 7.dp
    val ItemIconBoxSize = 30.dp
    val ItemIconSize = 23.dp
    val ItemBadgeSize = 7.dp
    val ItemLabelGap = 3.dp
    val ItemLabelText = 12.sp
}

private data class BiometricStatus(
    val available: Boolean,
    val message: String?,
)

private fun UserProfileDto.headerName(): String = displayName.ifBlank { username }

@Composable
fun MedtrackApp(
    container: MedtrackAppContainer,
    onAuthenticated: () -> Unit = {},
    notificationCaseId: String? = null,
    onNotificationCaseConsumed: () -> Unit = {},
) {
    val navController = rememberNavController()
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentDestination = backStackEntry?.destination
    var startDestination by remember { mutableStateOf<String?>(null) }
    var lastInteractionAt by remember { mutableStateOf(System.currentTimeMillis()) }
    var backgroundedAt by remember { mutableStateOf<Long?>(null) }
    val scope = rememberCoroutineScope()
    val syncConflicts by container.medtrackRepository.syncConflicts.collectAsState(initial = emptyList())
    val pendingWriteCount by container.medtrackRepository.pendingWriteCount.collectAsState(initial = 0)
    val shellNotifications by container.medtrackRepository.notifications.collectAsState(initial = emptyList())
    val snackbarHostState = remember { SnackbarHostState() }
    var currentUserDisplayName by remember { mutableStateOf<String?>(null) }
    var showQuickAddSheet by remember { mutableStateOf(false) }
    val currentRoute = currentDestination?.route
    val bottomRoutes = remember { bottomDestinations.map { it.route }.toSet() }
    val showBottomNav = currentRoute in bottomRoutes || currentRoute == Routes.NOTIFICATIONS

    fun shouldRelock(): Boolean {
        return currentRoute !in setOf(Routes.LOGIN, Routes.LOCK_SETUP, Routes.UNLOCK) &&
            container.authRepository.hasRefreshToken() &&
            container.lockStore.hasAnyLock()
    }

    fun navigateTopLevel(route: String) {
        navController.navigate(route) {
            launchSingleTop = true
            restoreState = true
            popUpTo(navController.graph.findStartDestination().id) {
                saveState = true
            }
        }
    }

    fun signOut() {
        scope.launch {
            val deviceToken = container.medtrackRepository.currentPushTokenForLogout()
            container.authRepository.logout(deviceToken = deviceToken)
            currentUserDisplayName = null
            navController.navigate(Routes.LOGIN) {
                popUpTo(navController.graph.findStartDestination().id) {
                    inclusive = true
                }
            }
        }
    }

    fun relockForIdle() {
        if (!shouldRelock()) return
        navController.navigate(Routes.UNLOCK) {
            launchSingleTop = true
            restoreState = false
            popUpTo(navController.graph.findStartDestination().id) {
                saveState = false
            }
        }
    }

    LaunchedEffect(container) {
        startDestination = if (container.authRepository.hasRefreshToken()) {
            if (container.lockStore.hasAnyLock()) Routes.UNLOCK else Routes.LOCK_SETUP
        } else {
            Routes.LOGIN
        }
    }

    DisposableEffect(lifecycleOwner, currentDestination?.route, startDestination) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_STOP -> {
                    backgroundedAt = System.currentTimeMillis()
                }
                Lifecycle.Event.ON_START -> {
                    val awayFor = backgroundedAt?.let { System.currentTimeMillis() - it } ?: 0L
                    backgroundedAt = null
                    if (awayFor >= IDLE_RELOCK_MILLIS) {
                        relockForIdle()
                    }
                }
                else -> Unit
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
        }
    }

    LaunchedEffect(lastInteractionAt, currentDestination?.route, startDestination) {
        delay(IDLE_RELOCK_MILLIS)
        if (System.currentTimeMillis() - lastInteractionAt >= IDLE_RELOCK_MILLIS) {
            relockForIdle()
        }
    }

    LaunchedEffect(notificationCaseId, currentDestination?.route, startDestination) {
        val caseId = notificationCaseId ?: return@LaunchedEffect
        val route = currentDestination?.route ?: return@LaunchedEffect
        if (route !in setOf(Routes.LOGIN, Routes.LOCK_SETUP, Routes.UNLOCK)) {
            navController.navigate(Routes.caseDetail(caseId)) {
                launchSingleTop = true
            }
            onNotificationCaseConsumed()
        }
    }

    MedtrackTheme {
        if (startDestination == null) {
            MedtrackPage(title = "MEDTRACK", modifier = Modifier.fillMaxSize()) {
                Text("Opening secure session")
            }
            return@MedtrackTheme
        }

        Scaffold(
            modifier = Modifier
                .fillMaxSize()
                .pointerInput(Unit) {
                    awaitPointerEventScope {
                        while (true) {
                            awaitPointerEvent()
                            lastInteractionAt = System.currentTimeMillis()
                        }
                    }
                },
            snackbarHost = { SnackbarHost(hostState = snackbarHostState) },
            bottomBar = {
                if (showBottomNav) {
                    MedtrackBottomBar(
                        currentRoute = if (currentRoute == Routes.NOTIFICATIONS) Routes.HOME else currentRoute,
                        unreadCount = shellNotifications.count { !it.isRead },
                        onNavigate = ::navigateTopLevel,
                        onQuickAdd = { showQuickAddSheet = true },
                    )
                }
            },
        ) { padding ->
            NavHost(
                navController = navController,
                startDestination = startDestination ?: Routes.LOGIN,
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding),
            ) {
                composable(Routes.LOGIN) {
                    LoginScreen(
                        modifier = Modifier.fillMaxSize(),
                        onLogin = { username, password ->
                            currentUserDisplayName = container.authRepository.login(username, password).headerName()
                            val hasLock = container.lockStore.hasAnyLock()
                            val nextRoute = if (hasLock) Routes.HOME else Routes.LOCK_SETUP
                            if (hasLock) {
                                onAuthenticated()
                            }
                            navController.navigate(nextRoute) {
                                popUpTo(Routes.LOGIN) { inclusive = true }
                            }
                        },
                    )
                }
                composable(Routes.LOCK_SETUP) {
                    var biometricEnabled by remember { mutableStateOf(container.lockStore.isBiometricEnabled()) }
                    var biometricMessage by remember { mutableStateOf<String?>(null) }
                    val biometricStatus = remember(biometricEnabled) { biometricStatus(context) }
                    LockSetupScreen(
                        modifier = Modifier.fillMaxSize(),
                        biometricEnabled = biometricEnabled,
                        biometricAvailable = biometricStatus.available,
                        biometricMessage = biometricMessage ?: biometricStatus.message,
                        onSavePattern = { pattern -> container.lockStore.savePattern(pattern) },
                        onEnableBiometric = {
                            biometricMessage = null
                            promptBiometric(
                                context = context,
                                onSuccess = {
                                    container.lockStore.setBiometricEnabled(true)
                                    biometricEnabled = true
                                    biometricMessage = "Biometric unlock is enabled."
                                },
                                onError = { biometricMessage = it },
                            )
                        },
                        onContinue = {
                            if (container.lockStore.hasAnyLock()) {
                                onAuthenticated()
                                navController.navigate(Routes.HOME) {
                                    popUpTo(Routes.LOCK_SETUP) { inclusive = true }
                                }
                            }
                        },
                    )
                }
                composable(Routes.UNLOCK) {
                    var biometricMessage by remember { mutableStateOf<String?>(null) }
                    val biometricStatus = remember { biometricStatus(context) }
                    UnlockScreen(
                        modifier = Modifier.fillMaxSize(),
                        patternEnabled = container.lockStore.hasPattern(),
                        biometricEnabled = container.lockStore.isBiometricEnabled(),
                        biometricAvailable = biometricStatus.available,
                        biometricMessage = biometricMessage ?: biometricStatus.message,
                        onPatternUnlock = { pattern ->
                            if (!container.lockStore.verifyPattern(pattern)) {
                                return@UnlockScreen "Pattern did not match."
                            }
                            return@UnlockScreen if (container.authRepository.restoreSession()) {
                                runCatching {
                                    currentUserDisplayName = container.authRepository.currentUser().headerName()
                                }
                                onAuthenticated()
                                navController.navigate(Routes.HOME) {
                                    popUpTo(Routes.UNLOCK) { inclusive = true }
                                }
                                null
                            } else {
                                navController.navigate(Routes.LOGIN) {
                                    popUpTo(Routes.UNLOCK) { inclusive = true }
                                }
                                "Session expired. Please sign in again."
                            }
                        },
                        onBiometricUnlock = {
                            biometricMessage = null
                            promptBiometric(
                                context = context,
                                onSuccess = {
                                    scope.launch {
                                        if (container.authRepository.restoreSession()) {
                                            runCatching {
                                                currentUserDisplayName = container.authRepository.currentUser().headerName()
                                            }
                                            onAuthenticated()
                                            navController.navigate(Routes.HOME) {
                                                popUpTo(Routes.UNLOCK) { inclusive = true }
                                            }
                                        } else {
                                            navController.navigate(Routes.LOGIN) {
                                                popUpTo(Routes.UNLOCK) { inclusive = true }
                                            }
                                        }
                                    }
                                },
                                onError = { biometricMessage = it },
                            )
                        },
                    )
                }
                composable(Routes.HOME) {
                    val stats by container.medtrackRepository.stats.collectAsState()
                    val categoryOptions by container.medtrackRepository.categoryOptions.collectAsState()
                    var selectedBucket by remember { mutableStateOf<String?>("today") }
                    var selectedScope by remember { mutableStateOf("me") }
                    var searchQuery by remember { mutableStateOf("") }
                    var selectedCategories by remember { mutableStateOf<Set<String>>(emptySet()) }
                    var selectedSubcategories by remember { mutableStateOf<Set<String>>(emptySet()) }
                    var isRefreshing by remember { mutableStateOf(false) }
                    var error by remember { mutableStateOf<String?>(null) }
                    var actionMessage by remember { mutableStateOf<String?>(null) }
                    var hadPendingWrites by remember { mutableStateOf(false) }
                    var dialedCase by remember { mutableStateOf<PatientCase?>(null) }
                    var dialerStartedAt by remember { mutableStateOf<Long?>(null) }
                    var leftForDialer by remember { mutableStateOf(false) }
                    var callOutcomeCase by remember { mutableStateOf<PatientCase?>(null) }
                    var callOutcomeAttemptedAt by remember { mutableStateOf<String?>(null) }
                    val pagedCasesFlow = remember(
                        selectedBucket,
                        searchQuery,
                        selectedScope,
                        selectedCategories,
                        selectedSubcategories,
                    ) {
                        container.medtrackRepository.pagedCases(
                            bucket = selectedBucket,
                            query = searchQuery,
                            assignedTo = selectedScope,
                            categories = selectedCategories.toList(),
                            subcategories = selectedSubcategories.toList(),
                        )
                    }
                    val pagedCases = pagedCasesFlow.collectAsLazyPagingItems()
                    val pagingRefreshError = (pagedCases.loadState.refresh as? LoadState.Error)?.error?.message
                    val pagingAppendError = (pagedCases.loadState.append as? LoadState.Error)?.error?.message

                    LaunchedEffect(Unit) {
                        if (currentUserDisplayName.isNullOrBlank()) {
                            runCatching {
                                currentUserDisplayName = container.authRepository.currentUser().headerName()
                            }
                        }
                    }

                    fun refreshHome() {
                        scope.launch {
                            isRefreshing = true
                            error = null
                            runCatching {
                                container.medtrackRepository.refreshCategoryOptions()
                            }
                                .onFailure { error = it.message ?: "Unable to refresh filters" }
                            pagedCases.refresh()
                            isRefreshing = false
                        }
                    }

                    fun submitCallOutcome(patientCase: PatientCase, outcome: String, note: String?, attemptedAt: String?) {
                        scope.launch {
                            runCatching {
                                container.medtrackRepository.logCallOutcome(
                                    caseId = patientCase.id,
                                    taskId = patientCase.nextTaskId,
                                    outcome = outcome,
                                    note = note,
                                    attemptedAt = attemptedAt,
                                )
                            }.onSuccess { result ->
                                actionMessage = result.message
                                refreshHome()
                            }.onFailure {
                                actionMessage = it.message ?: "Call logging failed"
                            }
                        }
                    }

                    fun completeTaskAfterUndoWindow(patientCase: PatientCase) {
                        val taskId = patientCase.nextTaskId
                        if (taskId == null) {
                            actionMessage = "No open task to complete"
                            return
                        }
                        scope.launch {
                            actionMessage = null
                            val snackbarResult = snackbarHostState.showSnackbar(
                                message = "Mark ${patientCase.patientName} done?",
                                actionLabel = "Undo",
                                withDismissAction = true,
                                duration = SnackbarDuration.Long,
                            )
                            if (snackbarResult == SnackbarResult.ActionPerformed) {
                                actionMessage = "Completion cancelled"
                                return@launch
                            }
                            runCatching {
                                container.medtrackRepository.completeTask(taskId = taskId, caseId = patientCase.id)
                            }.onSuccess { result ->
                                actionMessage = result.message
                                refreshHome()
                            }.onFailure {
                                actionMessage = it.message ?: "Task completion failed"
                            }
                        }
                    }

                    LaunchedEffect(Unit) {
                        runCatching { container.medtrackRepository.loadCachedCategoryOptions() }
                        runCatching { container.medtrackRepository.refreshCategoryOptions() }
                            .onFailure { error = it.message ?: "Unable to load filters" }
                    }

                    LaunchedEffect(pendingWriteCount) {
                        if (pendingWriteCount > 0) {
                            hadPendingWrites = true
                        } else if (hadPendingWrites) {
                            hadPendingWrites = false
                            actionMessage = null
                            error = null
                            refreshHome()
                        }
                    }

                    DisposableEffect(lifecycleOwner, dialedCase) {
                        val observer = LifecycleEventObserver { _, event ->
                            when (event) {
                                Lifecycle.Event.ON_STOP -> {
                                    if (dialedCase != null) {
                                        leftForDialer = true
                                    }
                                }
                                Lifecycle.Event.ON_START -> {
                                    val startedAt = dialerStartedAt
                                    val returnedFromDialer = dialedCase != null &&
                                        leftForDialer &&
                                        startedAt != null &&
                                        System.currentTimeMillis() - startedAt > 300L
                                    if (returnedFromDialer) {
                                        callOutcomeCase = dialedCase
                                        callOutcomeAttemptedAt = startedAt?.let(::utcTimestampFromMillis)
                                        dialedCase = null
                                        dialerStartedAt = null
                                        leftForDialer = false
                                    }
                                }
                                else -> Unit
                            }
                        }
                        lifecycleOwner.lifecycle.addObserver(observer)
                        onDispose {
                            lifecycleOwner.lifecycle.removeObserver(observer)
                        }
                    }

                    HomeScreen(
                        modifier = Modifier.fillMaxSize(),
                        cases = pagedCases,
                        stats = stats,
                        searchQuery = searchQuery,
                        selectedBucket = selectedBucket,
                        selectedScope = selectedScope,
                        categoryOptions = categoryOptions,
                        selectedCategories = selectedCategories,
                        selectedSubcategories = selectedSubcategories,
                        pendingWriteCount = pendingWriteCount,
                        isRefreshing = isRefreshing || pagedCases.loadState.refresh is LoadState.Loading,
                        isLoadingMore = pagedCases.loadState.append is LoadState.Loading,
                        error = error ?: pagingRefreshError ?: pagingAppendError,
                        actionMessage = actionMessage,
                        userDisplayName = currentUserDisplayName,
                        onSearchChanged = { query ->
                            searchQuery = query
                            error = null
                        },
                        onBucketSelected = { bucket ->
                            selectedBucket = bucket
                            error = null
                        },
                        onScopeSelected = { scopeValue ->
                            selectedScope = scopeValue
                            error = null
                        },
                        onFiltersApplied = { categories, subcategories ->
                            selectedCategories = categories
                            selectedSubcategories = subcategories
                            error = null
                        },
                        onCategoryFilterSelected = { patientCase ->
                            val categoryValue = categoryOptions.firstOrNull {
                                it.category == patientCase.category || it.label.equals(patientCase.category.label, ignoreCase = true)
                            }?.value ?: patientCase.category.label
                            val subcategoryValue = patientCase.subcategoryValue?.takeIf { it.isNotBlank() }
                            if (subcategoryValue == null) {
                                selectedCategories = setOf(categoryValue)
                                selectedSubcategories = emptySet()
                            } else {
                                selectedCategories = emptySet()
                                selectedSubcategories = setOf(subcategoryValue)
                            }
                            error = null
                        },
                        onRefresh = { refreshHome() },
                        onCallPatient = { patientCase ->
                            if (patientCase.phoneNumber.isNullOrBlank()) {
                                actionMessage = "No phone number on file"
                            } else {
                                dialedCase = patientCase
                                dialerStartedAt = System.currentTimeMillis()
                                leftForDialer = false
                                if (!openDialer(context, patientCase)) {
                                    dialedCase = null
                                    dialerStartedAt = null
                                    callOutcomeAttemptedAt = null
                                    actionMessage = "Unable to open dialer"
                                }
                            }
                        },
                        onMessagePatient = { patientCase ->
                            if (openWhatsApp(context, patientCase)) {
                                actionMessage = "Opening WhatsApp"
                            } else {
                                actionMessage = "No phone number on file"
                            }
                        },
                        onCompleteTask = { patientCase ->
                            completeTaskAfterUndoWindow(patientCase)
                        },
                        onOpenCase = { patientCase ->
                            navController.navigate(Routes.caseDetail(patientCase.id)) {
                                launchSingleTop = true
                            }
                        },
                        onOpenNotifications = { navController.navigate(Routes.NOTIFICATIONS) },
                        onSignOut = { signOut() },
                    )

                    callOutcomeCase?.let { patientCase ->
                        CallOutcomeSheet(
                            patientName = patientCase.patientName,
                            onOutcome = { outcome, note ->
                                val attemptedAt = callOutcomeAttemptedAt
                                callOutcomeCase = null
                                callOutcomeAttemptedAt = null
                                submitCallOutcome(patientCase, outcome, note, attemptedAt)
                            },
                            onAttempted = {
                                val attemptedAt = callOutcomeAttemptedAt
                                callOutcomeCase = null
                                callOutcomeAttemptedAt = null
                                submitCallOutcome(
                                    patientCase = patientCase,
                                    outcome = "attempted",
                                    note = "Mobile dialer opened; outcome was not confirmed.",
                                    attemptedAt = attemptedAt,
                                )
                            },
                        )
                    }
                }
                composable(Routes.CASES) {
                    val cases by container.medtrackRepository.cases.collectAsState(initial = emptyList())
                    var isRefreshing by remember { mutableStateOf(false) }
                    var error by remember { mutableStateOf<String?>(null) }

                    fun refreshCaseList() {
                        scope.launch {
                            isRefreshing = true
                            error = null
                            runCatching {
                                container.medtrackRepository.refreshCases(
                                    bucket = "all",
                                    assignedTo = "all",
                                )
                            }.onFailure {
                                error = it.message ?: "Unable to refresh cases"
                            }
                            isRefreshing = false
                        }
                    }

                    LaunchedEffect(Unit) {
                        refreshCaseList()
                    }

                    CaseListScreen(
                        modifier = Modifier.fillMaxSize(),
                        cases = cases,
                        isRefreshing = isRefreshing,
                        error = error,
                        onRefresh = { refreshCaseList() },
                        onOpenCase = { caseId -> navController.navigate(Routes.caseDetail(caseId)) },
                    )
                }
                composable(Routes.CASE_DETAIL) { entry ->
                    val cases by container.medtrackRepository.cases.collectAsState(initial = emptyList())
                    val caseId = entry.arguments?.getString("caseId").orEmpty()
                    val cachedCase by container.medtrackRepository.observeCase(caseId).collectAsState(initial = null)
                    val tasks by container.medtrackRepository.observeTasks(caseId).collectAsState(initial = emptyList())
                    val vitals by container.medtrackRepository.observeVitals(caseId).collectAsState(initial = emptyList())
                    val vitalsThresholds by container.medtrackRepository.vitalsThresholds.collectAsState()
                    var caseActionMessage by remember { mutableStateOf<String?>(null) }
                    var caseError by remember { mutableStateOf<String?>(null) }
                    var caseRefreshing by remember { mutableStateOf(false) }
                    var hadPendingWrites by remember(caseId) { mutableStateOf(false) }
                    var dialedCase by remember(caseId) { mutableStateOf<PatientCase?>(null) }
                    var dialerStartedAt by remember(caseId) { mutableStateOf<Long?>(null) }
                    var leftForDialer by remember(caseId) { mutableStateOf(false) }
                    var callOutcomeCase by remember(caseId) { mutableStateOf<PatientCase?>(null) }
                    var callOutcomeAttemptedAt by remember(caseId) { mutableStateOf<String?>(null) }
                    val patientCase = cachedCase ?: cases.firstOrNull { it.id == caseId }

                    fun refreshCaseDetail() {
                        if (caseId.isBlank()) return
                        scope.launch {
                            caseRefreshing = true
                            caseError = null
                            runCatching {
                                container.medtrackRepository.refreshVitalsThresholds()
                                container.medtrackRepository.refreshCaseDetail(caseId)
                            }
                                .onFailure { caseError = it.message ?: "Unable to refresh case" }
                            caseRefreshing = false
                        }
                    }

                    fun submitCaseCallOutcome(patientCase: PatientCase, outcome: String, note: String?, attemptedAt: String?) {
                        scope.launch {
                            runCatching {
                                container.medtrackRepository.logCallOutcome(
                                    caseId = patientCase.id,
                                    taskId = patientCase.nextTaskId,
                                    outcome = outcome,
                                    note = note,
                                    attemptedAt = attemptedAt,
                                )
                            }.onSuccess { result ->
                                caseActionMessage = result.message
                                if (!result.queued) {
                                    refreshCaseDetail()
                                    runCatching { container.medtrackRepository.refreshCases() }
                                }
                            }.onFailure {
                                caseActionMessage = it.message ?: "Call logging failed"
                            }
                        }
                    }

                    LaunchedEffect(caseId) {
                        runCatching { container.medtrackRepository.loadCachedVitalsThresholds() }
                        refreshCaseDetail()
                    }

                    LaunchedEffect(caseId, pendingWriteCount) {
                        if (pendingWriteCount > 0) {
                            hadPendingWrites = true
                        } else if (hadPendingWrites) {
                            hadPendingWrites = false
                            caseActionMessage = null
                            caseError = null
                            refreshCaseDetail()
                        }
                    }

                    DisposableEffect(lifecycleOwner, dialedCase) {
                        val observer = LifecycleEventObserver { _, event ->
                            when (event) {
                                Lifecycle.Event.ON_STOP -> {
                                    if (dialedCase != null) {
                                        leftForDialer = true
                                    }
                                }
                                Lifecycle.Event.ON_START -> {
                                    val startedAt = dialerStartedAt
                                    val returnedFromDialer = dialedCase != null &&
                                        leftForDialer &&
                                        startedAt != null &&
                                        System.currentTimeMillis() - startedAt > 300L
                                    if (returnedFromDialer) {
                                        callOutcomeCase = dialedCase
                                        callOutcomeAttemptedAt = startedAt?.let(::utcTimestampFromMillis)
                                        dialedCase = null
                                        dialerStartedAt = null
                                        leftForDialer = false
                                    }
                                }
                                else -> Unit
                            }
                        }
                        lifecycleOwner.lifecycle.addObserver(observer)
                        onDispose {
                            lifecycleOwner.lifecycle.removeObserver(observer)
                        }
                    }

                    CaseDetailScreen(
                        modifier = Modifier.fillMaxSize(),
                        caseId = caseId,
                        patientCase = patientCase,
                        tasks = tasks,
                        vitals = vitals,
                        vitalsThresholds = vitalsThresholds,
                        actionMessage = caseActionMessage,
                        isRefreshing = caseRefreshing,
                        error = caseError,
                        onRefresh = { refreshCaseDetail() },
                        onCompleteTask = { task ->
                            scope.launch {
                                runCatching {
                                    container.medtrackRepository.completeTask(taskId = task.id, caseId = caseId)
                                }.onSuccess { result ->
                                    caseActionMessage = result.message
                                    if (!result.queued) {
                                        refreshCaseDetail()
                                    }
                                }.onFailure {
                                    caseActionMessage = it.message ?: "Task completion failed"
                                }
                            }
                        },
                        onAddVitals = { input: VitalsEntryInput ->
                            scope.launch {
                                runCatching {
                                    container.medtrackRepository.addVitals(
                                        caseId = caseId,
                                        bpSystolic = input.bpSystolic,
                                        bpDiastolic = input.bpDiastolic,
                                        pulse = input.pulse,
                                        spo2 = input.spo2,
                                        weightKg = input.weightKg,
                                        hemoglobin = input.hemoglobin,
                                    )
                                }.onSuccess { result ->
                                    caseActionMessage = result.message
                                    if (!result.queued) {
                                        refreshCaseDetail()
                                        runCatching { container.medtrackRepository.refreshCases() }
                                    }
                                }.onFailure {
                                    caseActionMessage = it.message ?: "Vitals save failed"
                                }
                            }
                        },
                        onCallPatient = { selectedCase ->
                            if (selectedCase.phoneNumber.isNullOrBlank()) {
                                caseActionMessage = "No phone number on file"
                            } else {
                                dialedCase = selectedCase
                                dialerStartedAt = System.currentTimeMillis()
                                leftForDialer = false
                                if (!openDialer(context, selectedCase)) {
                                    dialedCase = null
                                    dialerStartedAt = null
                                    callOutcomeAttemptedAt = null
                                    caseActionMessage = "Unable to open dialer"
                                }
                            }
                        },
                        onMessagePatient = { selectedCase ->
                            caseActionMessage = if (openWhatsApp(context, selectedCase)) {
                                "Opening WhatsApp"
                            } else {
                                "No phone number on file"
                            }
                        },
                        onBack = { navController.popBackStack() },
                    )

                    callOutcomeCase?.let { selectedCase ->
                        CallOutcomeSheet(
                            patientName = selectedCase.patientName,
                            onOutcome = { outcome, note ->
                                val attemptedAt = callOutcomeAttemptedAt
                                callOutcomeCase = null
                                callOutcomeAttemptedAt = null
                                submitCaseCallOutcome(selectedCase, outcome, note, attemptedAt)
                            },
                            onAttempted = {
                                val attemptedAt = callOutcomeAttemptedAt
                                callOutcomeCase = null
                                callOutcomeAttemptedAt = null
                                submitCaseCallOutcome(
                                    patientCase = selectedCase,
                                    outcome = "attempted",
                                    note = "Mobile dialer opened; outcome was not confirmed.",
                                    attemptedAt = attemptedAt,
                                )
                            },
                        )
                    }
                }
                composable(Routes.CALLS) {
                    val cases by container.medtrackRepository.cases.collectAsState(initial = emptyList())
                    var isRefreshing by remember { mutableStateOf(false) }
                    var error by remember { mutableStateOf<String?>(null) }
                    var actionMessage by remember { mutableStateOf<String?>(null) }
                    var dialedCase by remember { mutableStateOf<PatientCase?>(null) }
                    var dialerStartedAt by remember { mutableStateOf<Long?>(null) }
                    var leftForDialer by remember { mutableStateOf(false) }
                    var callOutcomeCase by remember { mutableStateOf<PatientCase?>(null) }
                    var callOutcomeAttemptedAt by remember { mutableStateOf<String?>(null) }
                    var hadPendingWrites by remember { mutableStateOf(false) }

                    fun refreshCalls() {
                        scope.launch {
                            isRefreshing = true
                            error = null
                            runCatching {
                                container.medtrackRepository.refreshCases(
                                    bucket = "all",
                                    assignedTo = "all",
                                )
                            }.onFailure {
                                error = it.message ?: "Unable to refresh calls"
                            }
                            isRefreshing = false
                        }
                    }

                    fun submitCallOutcome(patientCase: PatientCase, outcome: String, note: String?, attemptedAt: String?) {
                        scope.launch {
                            runCatching {
                                container.medtrackRepository.logCallOutcome(
                                    caseId = patientCase.id,
                                    taskId = patientCase.nextTaskId,
                                    outcome = outcome,
                                    note = note,
                                    attemptedAt = attemptedAt,
                                )
                            }.onSuccess { result ->
                                actionMessage = result.message
                                refreshCalls()
                            }.onFailure {
                                actionMessage = it.message ?: "Call logging failed"
                            }
                        }
                    }

                    LaunchedEffect(Unit) {
                        refreshCalls()
                    }

                    LaunchedEffect(pendingWriteCount) {
                        if (pendingWriteCount > 0) {
                            hadPendingWrites = true
                        } else if (hadPendingWrites) {
                            hadPendingWrites = false
                            actionMessage = null
                            error = null
                            refreshCalls()
                        }
                    }

                    DisposableEffect(lifecycleOwner, dialedCase) {
                        val observer = LifecycleEventObserver { _, event ->
                            when (event) {
                                Lifecycle.Event.ON_STOP -> {
                                    if (dialedCase != null) {
                                        leftForDialer = true
                                    }
                                }
                                Lifecycle.Event.ON_START -> {
                                    val startedAt = dialerStartedAt
                                    val returnedFromDialer = dialedCase != null &&
                                        leftForDialer &&
                                        startedAt != null &&
                                        System.currentTimeMillis() - startedAt > 300L
                                    if (returnedFromDialer) {
                                        callOutcomeCase = dialedCase
                                        callOutcomeAttemptedAt = startedAt?.let(::utcTimestampFromMillis)
                                        dialedCase = null
                                        dialerStartedAt = null
                                        leftForDialer = false
                                    }
                                }
                                else -> Unit
                            }
                        }
                        lifecycleOwner.lifecycle.addObserver(observer)
                        onDispose {
                            lifecycleOwner.lifecycle.removeObserver(observer)
                        }
                    }

                    CallsScreen(
                        modifier = Modifier.fillMaxSize(),
                        cases = cases,
                        isRefreshing = isRefreshing,
                        error = error,
                        actionMessage = actionMessage,
                        onRefresh = { refreshCalls() },
                        onOpenCase = { caseId -> navController.navigate(Routes.caseDetail(caseId)) },
                        onCallPatient = { patientCase ->
                            dialedCase = patientCase
                            dialerStartedAt = System.currentTimeMillis()
                            leftForDialer = false
                            if (!openDialer(context, patientCase)) {
                                dialedCase = null
                                dialerStartedAt = null
                                callOutcomeAttemptedAt = null
                                actionMessage = "Unable to open dialer"
                            }
                        },
                        onMessagePatient = { patientCase ->
                            actionMessage = if (openWhatsApp(context, patientCase)) {
                                "Opening WhatsApp"
                            } else {
                                "Unable to open WhatsApp"
                            }
                        },
                    )

                    callOutcomeCase?.let { patientCase ->
                        CallOutcomeSheet(
                            patientName = patientCase.patientName,
                            onOutcome = { outcome, note ->
                                val attemptedAt = callOutcomeAttemptedAt
                                callOutcomeCase = null
                                callOutcomeAttemptedAt = null
                                submitCallOutcome(patientCase, outcome, note, attemptedAt)
                            },
                            onAttempted = {
                                val attemptedAt = callOutcomeAttemptedAt
                                callOutcomeCase = null
                                callOutcomeAttemptedAt = null
                                submitCallOutcome(
                                    patientCase = patientCase,
                                    outcome = "attempted",
                                    note = "Mobile dialer opened; outcome was not confirmed.",
                                    attemptedAt = attemptedAt,
                                )
                            },
                        )
                    }
                }
                composable(Routes.NOTIFICATIONS) {
                    val notifications by container.medtrackRepository.notifications.collectAsState(initial = emptyList())
                    var isRefreshing by remember { mutableStateOf(false) }
                    var error by remember { mutableStateOf<String?>(null) }

                    fun refreshNotifications() {
                        scope.launch {
                            isRefreshing = true
                            error = null
                            runCatching { container.medtrackRepository.refreshNotifications() }
                                .onFailure { error = it.message ?: "Unable to refresh notifications" }
                            isRefreshing = false
                        }
                    }

                    LaunchedEffect(Unit) {
                        refreshNotifications()
                    }

                    NotificationsScreen(
                        modifier = Modifier.fillMaxSize(),
                        notifications = notifications,
                        isRefreshing = isRefreshing,
                        error = error,
                        onRefresh = { refreshNotifications() },
                        onOpenNotification = { item ->
                            item.caseId?.let { caseId ->
                                scope.launch {
                                    runCatching { container.medtrackRepository.markNotificationRead(item.id) }
                                    navController.navigate(Routes.caseDetail(caseId))
                                }
                            }
                        },
                    )
                }
                composable(Routes.ME) {
                    LaunchedEffect(Unit) {
                        if (currentUserDisplayName.isNullOrBlank()) {
                            runCatching {
                                currentUserDisplayName = container.authRepository.currentUser().headerName()
                            }
                        }
                    }
                    ProfileScreen(
                        modifier = Modifier.fillMaxSize(),
                        displayName = currentUserDisplayName ?: "MEDTRACK user",
                        pendingWriteCount = pendingWriteCount,
                        unreadNotificationCount = shellNotifications.count { !it.isRead },
                        onOpenNotifications = { navController.navigate(Routes.NOTIFICATIONS) },
                        onSignOut = { signOut() },
                    )
                }
            }
        }

        if (showQuickAddSheet && showBottomNav) {
            QuickAddSheet(
                onDismiss = { showQuickAddSheet = false },
                onOpenCases = {
                    showQuickAddSheet = false
                    navigateTopLevel(Routes.CASES)
                },
                onOpenHomeSearch = {
                    showQuickAddSheet = false
                    navigateTopLevel(Routes.HOME)
                },
            )
        }

        syncConflicts.firstOrNull()?.takeIf {
            currentDestination?.route !in setOf(Routes.LOGIN, Routes.LOCK_SETUP, Routes.UNLOCK)
        }?.let { conflict ->
            AlertDialog(
                onDismissRequest = {
                    scope.launch { container.medtrackRepository.dismissSyncConflict(conflict.clientWriteId) }
                },
                title = { Text("Sync conflict") },
                text = { Text("Server version was kept for an offline change.") },
                confirmButton = {
                    TextButton(
                        onClick = {
                            conflict.caseId?.let { caseId ->
                                navController.navigate(Routes.caseDetail(caseId)) {
                                    launchSingleTop = true
                                }
                            }
                            scope.launch { container.medtrackRepository.dismissSyncConflict(conflict.clientWriteId) }
                        },
                    ) {
                        Text("View server version")
                    }
                },
                dismissButton = {
                    TextButton(
                        onClick = {
                            scope.launch { container.medtrackRepository.dismissSyncConflict(conflict.clientWriteId) }
                        },
                    ) {
                        Text("Dismiss")
                    }
                },
            )
        }
    }
}

@Composable
private fun MedtrackBottomBar(
    currentRoute: String?,
    unreadCount: Int,
    onNavigate: (String) -> Unit,
    onQuickAdd: () -> Unit,
) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(BottomNavScale.ShellHeight)
            .background(MedtrackColors.Card),
    ) {
        Surface(
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .fillMaxWidth()
                .height(BottomNavScale.BarHeight),
            shape = RoundedCornerShape(0.dp),
            color = MedtrackColors.Card,
            shadowElevation = 6.dp,
        ) {
            Row(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(horizontal = BottomNavScale.BarHorizontalPadding),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                BottomNavItem(bottomDestinations[0], currentRoute, onNavigate)
                BottomNavItem(bottomDestinations[1], currentRoute, onNavigate)
                Spacer(modifier = Modifier.width(BottomNavScale.CenterSpacerWidth))
                BottomNavItem(bottomDestinations[2], currentRoute, onNavigate)
                BottomNavItem(
                    destination = bottomDestinations[3],
                    currentRoute = currentRoute,
                    onNavigate = onNavigate,
                    badge = unreadCount.takeIf { it > 0 }?.coerceAtMost(9)?.toString(),
                )
            }
        }
        Surface(
            modifier = Modifier
                .align(Alignment.TopCenter)
                .offset(y = BottomNavScale.CenterButtonYOffset)
                .size(BottomNavScale.CenterButtonSize),
            shape = RoundedCornerShape(BottomNavScale.CenterButtonRadius),
            color = Color.Transparent,
            shadowElevation = 12.dp,
        ) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(
                        brush = Brush.horizontalGradient(
                            listOf(MedtrackColors.Primary, Color(0xFF4F46E5)),
                        ),
                        shape = RoundedCornerShape(BottomNavScale.CenterButtonRadius),
                    )
                    .clickable(onClick = onQuickAdd),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    imageVector = Icons.Outlined.Add,
                    contentDescription = "Quick add",
                    modifier = Modifier.size(BottomNavScale.CenterIconSize),
                    tint = Color.White,
                )
            }
        }
    }
}

@Composable
private fun RowScope.BottomNavItem(
    destination: BottomDestination,
    currentRoute: String?,
    onNavigate: (String) -> Unit,
    badge: String? = null,
) {
    val selected = currentRoute == destination.route
    val color = if (selected) MedtrackColors.Primary else MedtrackColors.Muted

    Box(
        modifier = Modifier
            .weight(1f)
            .fillMaxSize()
            .clickable { onNavigate(destination.route) }
            .padding(top = BottomNavScale.ItemPaddingTop, bottom = BottomNavScale.ItemPaddingBottom),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Box(
                modifier = Modifier.size(BottomNavScale.ItemIconBoxSize),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    imageVector = destination.icon,
                    contentDescription = destination.label,
                    modifier = Modifier.size(BottomNavScale.ItemIconSize),
                    tint = color,
                )
                badge?.let {
                    Box(
                        modifier = Modifier
                            .align(Alignment.TopEnd)
                            .size(BottomNavScale.ItemBadgeSize)
                            .background(MedtrackColors.Danger, CircleShape),
                    )
                }
            }
            Spacer(modifier = Modifier.height(BottomNavScale.ItemLabelGap))
            Text(
                text = destination.label,
                maxLines = 1,
                color = color,
                style = MaterialTheme.typography.labelSmall.copy(fontSize = BottomNavScale.ItemLabelText),
                fontWeight = if (selected) FontWeight.Bold else FontWeight.SemiBold,
            )
        }
    }
}

@Composable
@OptIn(ExperimentalMaterial3Api::class)
private fun QuickAddSheet(
    onDismiss: () -> Unit,
    onOpenCases: () -> Unit,
    onOpenHomeSearch: () -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = MedtrackColors.Surface,
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(start = 18.dp, end = 18.dp, bottom = 26.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(
                        text = "Quick add",
                        color = MedtrackColors.Ink,
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        text = "Search first, then create from web intake.",
                        color = MedtrackColors.Muted,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                MedtrackIconBadge(icon = Icons.Outlined.HealthAndSafety, tint = MedtrackColors.Primary)
            }

            MedtrackCompactCard {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    MedtrackIconBadge(icon = Icons.Outlined.Search, tint = MedtrackColors.Primary)
                    Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text("Find existing patient", fontWeight = FontWeight.Bold, color = MedtrackColors.Ink)
                        Text("Uses the current case list and filters.", color = MedtrackColors.Muted, style = MaterialTheme.typography.bodySmall)
                    }
                }
                Button(onClick = onOpenHomeSearch, modifier = Modifier.fillMaxWidth()) {
                    Text("Search home")
                }
            }

            MedtrackSectionTitle(title = "Pathways", trailing = "web-backed")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                QuickAddPathway("ANC", CaseCategory.ANC, Modifier.weight(1f))
                QuickAddPathway("Surgery", CaseCategory.SURGERY, Modifier.weight(1f))
                QuickAddPathway("Medicine", CaseCategory.MEDICINE, Modifier.weight(1f))
            }

            Surface(
                shape = RoundedCornerShape(14.dp),
                color = MedtrackColors.WarningSoft,
                border = BorderStroke(1.dp, MedtrackColors.Warning.copy(alpha = 0.24f)),
            ) {
                Text(
                    text = "New case entry is handled on the web for now.",
                    color = MedtrackColors.Warning,
                    style = MaterialTheme.typography.bodySmall,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.padding(12.dp),
                )
            }

            Button(
                onClick = onOpenCases,
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(containerColor = MedtrackColors.Ink),
            ) {
                Text("Open case list")
            }
        }
    }
}

@Composable
private fun QuickAddPathway(
    label: String,
    category: CaseCategory,
    modifier: Modifier = Modifier,
) {
    val color = categoryColor(category)
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(14.dp),
        color = color.copy(alpha = 0.11f),
        border = BorderStroke(1.dp, color.copy(alpha = 0.22f)),
    ) {
        Column(
            modifier = Modifier.padding(10.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            MedtrackIconBadge(icon = Icons.Outlined.Add, tint = color, modifier = Modifier.size(34.dp))
            Text(
                text = label,
                color = color,
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Bold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
private fun ProfileScreen(
    displayName: String,
    pendingWriteCount: Int,
    unreadNotificationCount: Int,
    onOpenNotifications: () -> Unit,
    onSignOut: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .background(MedtrackColors.Surface)
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Surface(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(24.dp),
            color = Color.Transparent,
        ) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(
                        Brush.linearGradient(
                            listOf(MedtrackColors.PrimaryDark, MedtrackColors.Primary),
                        ),
                    )
                    .padding(16.dp),
            ) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Surface(shape = CircleShape, color = Color.White.copy(alpha = 0.18f), modifier = Modifier.size(54.dp)) {
                        Box(contentAlignment = Alignment.Center) {
                            Text(
                                text = displayName.initials(),
                                color = Color.White,
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.Bold,
                            )
                        }
                    }
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(
                            text = displayName,
                            color = Color.White,
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        Text(
                            text = "MEDTRACK mobile session",
                            color = Color.White.copy(alpha = 0.82f),
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
            }
        }

        MedtrackCompactCard {
            MedtrackSectionTitle(title = "Today")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                MedtrackMiniPill(
                    text = "$pendingWriteCount pending sync",
                    color = if (pendingWriteCount > 0) MedtrackColors.Warning else MedtrackColors.Success,
                )
                MedtrackMiniPill(
                    text = "$unreadNotificationCount unread alerts",
                    color = if (unreadNotificationCount > 0) MedtrackColors.Danger else MedtrackColors.Muted,
                )
            }
        }

        MedtrackCompactCard(
            modifier = Modifier.clickable(onClick = onOpenNotifications),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                MedtrackIconBadge(icon = Icons.Outlined.Sync, tint = MedtrackColors.Primary)
                Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text("Notifications and sync", fontWeight = FontWeight.Bold, color = MedtrackColors.Ink)
                    Text("View alerts and queued mobile work.", color = MedtrackColors.Muted, style = MaterialTheme.typography.bodySmall)
                }
            }
        }

        Spacer(modifier = Modifier.weight(1f))
        Button(
            onClick = onSignOut,
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(containerColor = MedtrackColors.Ink),
        ) {
            Icon(imageVector = Icons.Outlined.Logout, contentDescription = null)
            Spacer(modifier = Modifier.width(8.dp))
            Text("Sign out")
        }
    }
}

private fun categoryColor(category: CaseCategory): Color =
    when (category) {
        CaseCategory.ANC -> MedtrackColors.Anc
        CaseCategory.SURGERY -> MedtrackColors.Surgery
        CaseCategory.MEDICINE -> MedtrackColors.Medicine
        CaseCategory.OTHER -> MedtrackColors.Primary
    }

private fun String.initials(): String {
    val parts = trim().split(Regex("\\s+")).filter { it.isNotBlank() }
    return parts.take(2).joinToString("") { it.take(1).uppercase(Locale.getDefault()) }.ifBlank { "M" }
}

private fun openDialer(context: android.content.Context, patientCase: PatientCase): Boolean {
    val number = patientCase.phoneNumber?.takeIf { it.isNotBlank() } ?: return false
    val intent = Intent(Intent.ACTION_DIAL).apply {
        data = Uri.parse("tel:$number")
    }
    return try {
        context.startActivity(intent)
        true
    } catch (_: ActivityNotFoundException) {
        false
    }
}

private fun openWhatsApp(context: android.content.Context, patientCase: PatientCase): Boolean {
    val number = patientCase.phoneNumber?.toWaMeNumber() ?: return false
    val intent = Intent(Intent.ACTION_VIEW).apply {
        data = Uri.parse("https://wa.me/$number")
    }
    return try {
        context.startActivity(intent)
        true
    } catch (_: ActivityNotFoundException) {
        false
    }
}

private fun String.toWaMeNumber(): String? {
    val trimmed = trim()
    if (trimmed.isBlank()) return null

    val hasPlus = trimmed.startsWith("+")
    val digits = trimmed.filter(Char::isDigit)
    if (digits.isBlank()) return null

    return when {
        hasPlus -> digits
        digits.length == 10 -> "91$digits"
        digits.length == 11 && digits.startsWith("0") -> "91${digits.drop(1)}"
        else -> digits
    }
}

private fun utcTimestampFromMillis(millis: Long): String =
    SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
        timeZone = TimeZone.getTimeZone("UTC")
    }.format(Date(millis))

private fun biometricStatus(context: Context): BiometricStatus {
    val status = BiometricManager.from(context).canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_WEAK)
    return when (status) {
        BiometricManager.BIOMETRIC_SUCCESS -> BiometricStatus(available = true, message = null)
        BiometricManager.BIOMETRIC_ERROR_NONE_ENROLLED -> BiometricStatus(
            available = false,
            message = "No biometric is enrolled on this device.",
        )
        BiometricManager.BIOMETRIC_ERROR_NO_HARDWARE -> BiometricStatus(
            available = false,
            message = "This device does not have biometric hardware.",
        )
        BiometricManager.BIOMETRIC_ERROR_HW_UNAVAILABLE -> BiometricStatus(
            available = false,
            message = "Biometric hardware is currently unavailable.",
        )
        else -> BiometricStatus(
            available = false,
            message = "Biometric unlock is not available on this device.",
        )
    }
}

private fun promptBiometric(
    context: Context,
    onSuccess: () -> Unit,
    onError: (String) -> Unit,
) {
    val activity = context as? FragmentActivity ?: run {
        onError("Biometric unlock is unavailable in this screen.")
        return
    }
    val prompt = BiometricPrompt(
        activity,
        ContextCompat.getMainExecutor(context),
        object : BiometricPrompt.AuthenticationCallback() {
            override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                onError(errString.toString())
            }

            override fun onAuthenticationFailed() {
                onError("Biometric was not recognized.")
            }

            override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                onSuccess()
            }
        },
    )
    val promptInfo = BiometricPrompt.PromptInfo.Builder()
        .setTitle("Unlock MEDTRACK")
        .setSubtitle("Use your device biometric")
        .setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_WEAK)
        .setNegativeButtonText("Cancel")
        .build()
    prompt.authenticate(promptInfo)
}
