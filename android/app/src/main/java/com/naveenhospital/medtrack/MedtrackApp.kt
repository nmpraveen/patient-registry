package com.naveenhospital.medtrack

import androidx.activity.compose.BackHandler
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
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
import androidx.core.net.toUri
import androidx.fragment.app.FragmentActivity
import androidx.compose.runtime.DisposableEffect
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Phone
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.AssignmentInd
import androidx.compose.material.icons.outlined.CheckCircle
import androidx.compose.material.icons.outlined.ChevronRight
import androidx.compose.material.icons.outlined.CloudDone
import androidx.compose.material.icons.outlined.ErrorOutline
import androidx.compose.material.icons.outlined.Notifications
import androidx.compose.material.icons.outlined.Schedule
import androidx.compose.material.icons.outlined.Folder
import androidx.compose.material.icons.outlined.HealthAndSafety
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material.icons.outlined.Person
import androidx.compose.material.icons.outlined.Phone
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.Search
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
import androidx.compose.ui.res.painterResource
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
import com.naveenhospital.medtrack.core.designsystem.R as DesignR
import com.naveenhospital.medtrack.core.designsystem.MedtrackColors
import com.naveenhospital.medtrack.core.designsystem.MedtrackElevation
import com.naveenhospital.medtrack.core.designsystem.MedtrackIconBadge
import com.naveenhospital.medtrack.core.designsystem.MedtrackTheme
import com.naveenhospital.medtrack.core.designsystem.MedtrackPage
import com.naveenhospital.medtrack.core.designsystem.MedtrackSectionTitle
import com.naveenhospital.medtrack.core.data.sync.PendingWriteTypes
import com.naveenhospital.medtrack.core.data.auth.LockVerificationResult
import com.naveenhospital.medtrack.core.data.auth.SessionRestoreResult
import com.naveenhospital.medtrack.core.domain.model.CategoryFilterOption
import com.naveenhospital.medtrack.core.domain.model.CallOutcomeInput
import com.naveenhospital.medtrack.core.domain.model.CallTaskChoice
import com.naveenhospital.medtrack.core.data.repository.MedtrackRepository
import com.naveenhospital.medtrack.core.domain.model.PatientCase
import com.naveenhospital.medtrack.core.domain.model.CaseCategory
import com.naveenhospital.medtrack.core.domain.model.NotificationItem
import com.naveenhospital.medtrack.core.domain.model.SyncConflict
import com.naveenhospital.medtrack.core.network.model.UserProfileDto
import com.naveenhospital.medtrack.feature.auth.LockSetupScreen
import com.naveenhospital.medtrack.feature.auth.LoginScreen
import com.naveenhospital.medtrack.feature.auth.UnlockScreen
import com.naveenhospital.medtrack.feature.calls.CallOutcomeSheet
import com.naveenhospital.medtrack.feature.calls.CallsScreen
import com.naveenhospital.medtrack.feature.cases.CaseCreationScreen
import com.naveenhospital.medtrack.feature.cases.CaseDetailScreen
import com.naveenhospital.medtrack.feature.cases.CaseEditScreen
import com.naveenhospital.medtrack.feature.cases.CaseListScreen
import com.naveenhospital.medtrack.feature.cases.TaskSheetAction
import com.naveenhospital.medtrack.feature.cases.VitalsEntryInput
import com.naveenhospital.medtrack.core.domain.model.TaskFormMetadata
import com.naveenhospital.medtrack.core.domain.model.TaskWriteOutcome
import com.naveenhospital.medtrack.core.domain.model.VitalsWriteOutcome
import com.naveenhospital.medtrack.feature.home.HomeScreen
import com.naveenhospital.medtrack.feature.notifications.AlertDetailScreen
import com.naveenhospital.medtrack.feature.notifications.NotificationsScreen
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import kotlinx.coroutines.delay
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import com.naveenhospital.medtrack.operations.StaffToolsScreen
import com.naveenhospital.medtrack.operations.StaffSummaryBanner
import androidx.compose.material3.OutlinedButton

private const val IDLE_RELOCK_MILLIS = 15 * 60 * 1000L
private const val UI_REVIEW_AUTO_LOGIN = false
private const val UI_REVIEW_USERNAME = "admin"
private const val UI_REVIEW_PASSWORD = "pass"

private val uiReviewAutoLoginEnabled: Boolean
    get() = BuildConfig.DEBUG && UI_REVIEW_AUTO_LOGIN

private object Routes {
    const val LOGIN = "login"
    const val LOCK_SETUP = "lock_setup"
    const val UNLOCK = "unlock"
    const val HOME = "home"
    const val CASES = "cases"
    const val CASE_DETAIL = "cases/{caseId}"
    const val CREATE_CASE = "create_case/{category}/{label}"
    const val EDIT_CASE = "edit_case/{caseId}"
    const val CALLS = "calls"
    const val NOTIFICATIONS = "notifications"
    const val ALERT_DETAIL = "alerts/{notificationId}"
    const val ME = "me"
    const val STAFF_TOOLS = "staff_tools/{tab}"

    fun caseDetail(caseId: String): String = "cases/$caseId"
    fun createCase(category: CaseCategory, label: String): String = "create_case/${category.name}/${Uri.encode(label)}"
    fun editCase(caseId: String): String = "edit_case/$caseId"
    fun alertDetail(notificationId: String): String = "alerts/${Uri.encode(notificationId)}"
}

private data class BottomDestination(
    val route: String,
    val label: String,
    val icon: ImageVector,
    val selectedIcon: ImageVector,
)

private val bottomDestinations = listOf(
    BottomDestination(Routes.HOME, "Home", Icons.Outlined.Home, Icons.Filled.Home),
    BottomDestination(Routes.CASES, "Cases", Icons.Outlined.Folder, Icons.Filled.Folder),
    BottomDestination(Routes.CALLS, "Calls", Icons.Outlined.Phone, Icons.Filled.Phone),
    BottomDestination(Routes.ME, "Me", Icons.Outlined.Person, Icons.Filled.Person),
)

private object BottomNavScale {
    // Detached, floating frosted bar with a dot indicator above the active icon.
    val BarHeight = 72.dp
    // Inset from the screen edges so the bar reads as a floating card.
    val BarHorizontalInset = 16.dp
    // Gap between the bar and the bottom edge of the shell.
    val BarBottomInset = 16.dp
    // The bar is an overlay that content slides underneath, so the shell only wraps
    // the bar itself (bar height + bottom inset); no reserved "moat" is needed.
    val ShellHeight = BarHeight + BarBottomInset
    val BarCornerRadius = 28.dp
    val BarBorderWidth = 1.dp
    val CenterColumnWidth = 76.dp
    val CenterButtonSize = 58.dp
    val CenterButtonRadius = 20.dp
    val CenterIconSize = 30.dp
    val ItemIconBoxSize = 32.dp
    val ItemIconSize = 25.dp
    // Small dot marker that sits just above the icon for the selected tab.
    val ItemDotSize = 5.dp
    // Gap between the indicator dot and the icon below it.
    val ItemDotTopGap = 5.dp
    val ItemLabelGap = 4.dp
    val ItemLabelText = 12.sp
}

private data class BiometricStatus(
    val available: Boolean,
    val message: String?,
)

private fun UserProfileDto.headerName(): String = displayName.ifBlank { username }

private fun UserProfileDto?.mobileDefaultCaseScope(): String {
    return if (this?.dataScope?.caseDataScope.equals("ALL", ignoreCase = true)) "all" else "me"
}

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
    val cachedCases by container.medtrackRepository.cases.collectAsState(initial = emptyList())
    val shellCategoryOptions by container.medtrackRepository.categoryOptions.collectAsState(initial = emptyList())
    val snackbarHostState = remember { SnackbarHostState() }
    val staffSession by container.staffToolsRepository.activeSession.collectAsState()
    var currentUserProfile by remember { mutableStateOf<UserProfileDto?>(null) }
    var currentUserDisplayName by remember { mutableStateOf<String?>(null) }
    var showQuickAddSheet by remember { mutableStateOf(false) }
    var lockSetupRequiresSessionRestore by remember { mutableStateOf(false) }
    // Hoisted so the Quick Add sheet's search can pre-fill the Home search query.
    var homeSearchQuery by remember { mutableStateOf("") }
    // Notification type the Notifications screen is scoped to (null = all). Set by the
    // Me-page category rows before navigating to the Notifications screen.
    var notificationsFilterType by remember { mutableStateOf<String?>(null) }
    val currentRoute = currentDestination?.route
    val bottomRoutes = remember { bottomDestinations.map { it.route }.toSet() }
    val showBottomNav = currentRoute in bottomRoutes || currentRoute == Routes.NOTIFICATIONS

    fun shouldRelock(): Boolean {
        if (uiReviewAutoLoginEnabled) return false
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

    fun setCurrentUser(profile: UserProfileDto) {
        currentUserProfile = profile
        currentUserDisplayName = profile.headerName()
    }

    fun routeAfterPasswordLogin(): String =
        if (container.lockStore.hasAnyLock()) Routes.HOME else Routes.LOCK_SETUP

    fun signOut() {
        // Clear app-scoped UI state so one user's search/filter never carries into the
        // next session on a shared device.
        homeSearchQuery = ""
        notificationsFilterType = null
        scope.launch {
            if (uiReviewAutoLoginEnabled) {
                runCatching {
                    setCurrentUser(container.authRepository.login(UI_REVIEW_USERNAME, UI_REVIEW_PASSWORD))
                }
                navController.navigate(Routes.HOME) {
                    popUpTo(navController.graph.findStartDestination().id) {
                        inclusive = true
                    }
                }
                return@launch
            }
            val deviceToken = container.medtrackRepository.currentPushTokenForLogout()
            container.authRepository.logout(deviceToken = deviceToken)
            currentUserProfile = null
            currentUserDisplayName = null
            lockSetupRequiresSessionRestore = false
            navController.navigate(Routes.LOGIN) {
                popUpTo(navController.graph.findStartDestination().id) {
                    inclusive = true
                }
            }
        }
    }

    LaunchedEffect(showQuickAddSheet) {
        if (showQuickAddSheet && shellCategoryOptions.isEmpty()) {
            runCatching { container.medtrackRepository.loadCachedCategoryOptions() }
            runCatching { container.medtrackRepository.refreshCategoryOptions() }
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
        if (uiReviewAutoLoginEnabled) {
            runCatching {
                setCurrentUser(container.authRepository.login(UI_REVIEW_USERNAME, UI_REVIEW_PASSWORD))
                onAuthenticated()
            }
            startDestination = Routes.HOME
            return@LaunchedEffect
        }
        val hasRefreshToken = container.authRepository.hasRefreshToken()
        val hasAnyLock = container.lockStore.hasAnyLock()
        lockSetupRequiresSessionRestore = hasRefreshToken && !hasAnyLock
        startDestination = if (hasRefreshToken) {
            if (hasAnyLock) Routes.UNLOCK else Routes.LOCK_SETUP
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
            snackbarHost = {
                // The nav bar is a floating overlay (not a Scaffold bottomBar slot), so the
                // Scaffold reserves no space for it. Lift the snackbar above the floating bar
                // on bottom-nav routes so Undo / dialer-error snackbars aren't overlapped.
                SnackbarHost(
                    hostState = snackbarHostState,
                    modifier = Modifier.padding(
                        bottom = if (showBottomNav) BottomNavScale.ShellHeight else 0.dp,
                    ),
                )
            },
        ) { padding ->
            // The bottom bar is an overlay (not a Scaffold bottomBar slot) so it
            // floats on top of the content and screen lists slide underneath it.
            // Scrollable screens already reserve ~104dp bottom content padding so
            // their last rows can be scrolled clear of the floating bar.
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding),
            ) {
            NavHost(
                navController = navController,
                startDestination = startDestination ?: Routes.LOGIN,
                modifier = Modifier.fillMaxSize(),
            ) {
                composable(Routes.LOGIN) {
                    LoginScreen(
                        modifier = Modifier.fillMaxSize(),
                        onLogin = { username, password ->
                            // Start every fresh login with clean app-scoped UI state.
                            homeSearchQuery = ""
                            notificationsFilterType = null
                            setCurrentUser(container.authRepository.login(username, password))
                            val nextRoute = routeAfterPasswordLogin()
                            lockSetupRequiresSessionRestore = false
                            if (nextRoute == Routes.HOME) {
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
                            if (!container.lockStore.hasAnyLock()) {
                                return@LockSetupScreen
                            }
                            scope.launch {
                                if (lockSetupRequiresSessionRestore) {
                                    when (val restored = container.authRepository.restoreSession()) {
                                        is SessionRestoreResult.Verified -> {
                                            setCurrentUser(restored.profile)
                                            lockSetupRequiresSessionRestore = false
                                        }
                                        is SessionRestoreResult.Retryable -> {
                                            snackbarHostState.showSnackbar(
                                                "Unable to verify the session. Check the connection and retry.",
                                            )
                                            return@launch
                                        }
                                        SessionRestoreResult.NoSession -> {
                                            currentUserProfile = null
                                            currentUserDisplayName = null
                                            lockSetupRequiresSessionRestore = false
                                            snackbarHostState.showSnackbar("Session expired. Please sign in again.")
                                            navController.navigate(Routes.LOGIN) {
                                                popUpTo(Routes.LOCK_SETUP) { inclusive = true }
                                            }
                                            return@launch
                                        }
                                    }
                                }
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
                            when (val verification = container.lockStore.verifyPattern(pattern)) {
                                LockVerificationResult.Invalid -> return@UnlockScreen "Pattern did not match."
                                is LockVerificationResult.Throttled -> {
                                    val seconds = (verification.retryAfterMillis + 999L) / 1_000L
                                    return@UnlockScreen "Too many attempts. Try again in $seconds seconds."
                                }
                                LockVerificationResult.ReauthenticationRequired -> {
                                    container.abandonLockedSession()
                                    navController.navigate(Routes.LOGIN) {
                                        popUpTo(Routes.UNLOCK) { inclusive = true }
                                    }
                                    return@UnlockScreen "Local unlock was reset. Sign in again."
                                }
                                LockVerificationResult.Success -> Unit
                            }
                            return@UnlockScreen when (val restored = container.authRepository.restoreSession()) {
                                is SessionRestoreResult.Verified -> {
                                    setCurrentUser(restored.profile)
                                    onAuthenticated()
                                    navController.navigate(Routes.HOME) {
                                        popUpTo(Routes.UNLOCK) { inclusive = true }
                                    }
                                    null
                                }
                                is SessionRestoreResult.Retryable ->
                                    "Unable to verify the session. Check the connection and retry."
                                SessionRestoreResult.NoSession -> {
                                    navController.navigate(Routes.LOGIN) {
                                        popUpTo(Routes.UNLOCK) { inclusive = true }
                                    }
                                    "Session expired. Please sign in again."
                                }
                            }
                        },
                        onBiometricUnlock = {
                            biometricMessage = null
                            promptBiometric(
                                context = context,
                                onSuccess = {
                                    scope.launch {
                                        when (val restored = container.authRepository.restoreSession()) {
                                            is SessionRestoreResult.Verified -> {
                                                setCurrentUser(restored.profile)
                                                onAuthenticated()
                                                navController.navigate(Routes.HOME) {
                                                    popUpTo(Routes.UNLOCK) { inclusive = true }
                                                }
                                            }
                                            is SessionRestoreResult.Retryable -> {
                                                biometricMessage =
                                                    "Unable to verify the session. Check the connection and retry."
                                            }
                                            SessionRestoreResult.NoSession -> {
                                                navController.navigate(Routes.LOGIN) {
                                                    popUpTo(Routes.UNLOCK) { inclusive = true }
                                                }
                                            }
                                        }
                                    }
                                },
                                onError = { biometricMessage = it },
                            )
                        },
                        onUsePasswordLogin = {
                            biometricMessage = null
                            currentUserProfile = null
                            currentUserDisplayName = null
                            lockSetupRequiresSessionRestore = false
                            scope.launch {
                                container.abandonLockedSession()
                                navController.navigate(Routes.LOGIN) {
                                    popUpTo(Routes.UNLOCK) { inclusive = true }
                                }
                            }
                        },
                    )
                }
                composable(Routes.HOME) {
                    val stats by container.medtrackRepository.stats.collectAsState()
                    val categoryOptions by container.medtrackRepository.categoryOptions.collectAsState()
                    val vitalsThresholds by container.medtrackRepository.vitalsThresholds.collectAsState()
                    var selectedBucket by remember { mutableStateOf<String?>("today") }
                    val defaultCaseScope = currentUserProfile.mobileDefaultCaseScope()
                    var selectedScope by remember(currentUserProfile?.id, defaultCaseScope) {
                        mutableStateOf(defaultCaseScope)
                    }
                    var selectedCategories by remember { mutableStateOf<Set<String>>(emptySet()) }
                    var selectedSubcategories by remember { mutableStateOf<Set<String>>(emptySet()) }
                    var isRefreshing by remember { mutableStateOf(false) }
                    var error by remember { mutableStateOf<String?>(null) }
                    var actionMessage by remember { mutableStateOf<String?>(null) }
                    var hadPendingWrites by remember { mutableStateOf(false) }
                    val dialerHandoff = rememberDialerHandoff()
                    val pagedCasesFlow = remember(
                        selectedBucket,
                        homeSearchQuery,
                        selectedScope,
                        selectedCategories,
                        selectedSubcategories,
                    ) {
                        container.medtrackRepository.pagedCases(
                            bucket = selectedBucket,
                            query = homeSearchQuery,
                            assignedTo = selectedScope,
                            categories = selectedCategories.toList(),
                            subcategories = selectedSubcategories.toList(),
                        )
                    }
                    val pagedCases = pagedCasesFlow.collectAsLazyPagingItems()
                    val pagingRefreshError = (pagedCases.loadState.refresh as? LoadState.Error)?.error?.message
                    val pagingAppendError = (pagedCases.loadState.append as? LoadState.Error)?.error?.message

                    LaunchedEffect(Unit) {
                        if (currentUserProfile == null) {
                            runCatching {
                                setCurrentUser(container.authRepository.currentUser())
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

                    fun submitCallOutcome(patientCase: PatientCase, input: CallOutcomeInput, attemptedAt: String?, report: (String?) -> Unit) {
                        scope.launch {
                            runCatching {
                                container.medtrackRepository.logCallOutcome(
                                    caseId = patientCase.id,
                                    taskId = input.taskId,
                                    reason = input.reason,
                                    outcome = input.outcome,
                                    note = input.note,
                                    attemptedAt = attemptedAt,
                                )
                            }.onSuccess { result ->
                                report(if (result.conflict) result.message else null)
                                actionMessage = result.message
                                refreshHome()
                            }.onFailure {
                                report(it.message ?: "Call logging failed")
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
                        runCatching { container.medtrackRepository.loadCachedVitalsThresholds() }
                        runCatching { container.medtrackRepository.refreshVitalsThresholds() }
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

                    HomeScreen(
                        loadUpcoming = { date, cursor -> container.medtrackRepository.loadUpcoming(
                            startDate = date, cursor = cursor, query = homeSearchQuery,
                            categories = selectedCategories.sorted(), subcategories = selectedSubcategories.sorted(),
                            assignedTo = selectedScope,
                        ) },
                        onOpenUpcomingCase = { id -> navController.navigate(Routes.caseDetail(id)) },
                        modifier = Modifier.fillMaxSize(),
                        staffSummary = { if (staffSession != null) StaffSummaryBanner(container.staffToolsRepository) { tab -> navController.navigate("staff_tools/$tab") } },
                        cases = pagedCases,
                        stats = stats,
                        searchQuery = homeSearchQuery,
                        selectedBucket = selectedBucket,
                        selectedScope = selectedScope,
                        categoryOptions = categoryOptions,
                        selectedCategories = selectedCategories,
                        selectedSubcategories = selectedSubcategories,
                        vitalsThresholds = vitalsThresholds,
                        pendingWriteCount = pendingWriteCount,
                        isRefreshing = isRefreshing || pagedCases.loadState.refresh is LoadState.Loading,
                        isLoadingMore = pagedCases.loadState.append is LoadState.Loading,
                        error = error ?: pagingRefreshError ?: pagingAppendError,
                        actionMessage = actionMessage,
                        onSearchChanged = { query ->
                            homeSearchQuery = query
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
                                it.label.equals(patientCase.categoryLabel, ignoreCase = true) || it.category == patientCase.category
                            }?.value ?: patientCase.categoryLabel
                            // Specialty card icons are subcategory-specific, so tapping one
                            // filters by that subcategory. The active filter chips still show
                            // and clear it even though the filter sheet stays categories-only.
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
                            dialerHandoff.startCall(context, patientCase) { actionMessage = it }
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
                    )

                    DialerOutcomeSheet(dialerHandoff, container.medtrackRepository) { selectedCase, input, attemptedAt, report ->
                        submitCallOutcome(selectedCase, input, attemptedAt, report)
                    }
                }
                composable(Routes.CASES) {
                    val cases by container.medtrackRepository.cases.collectAsState(initial = emptyList())
                    var isRefreshing by remember { mutableStateOf(false) }
                    var error by remember { mutableStateOf<String?>(null) }
                    val dialerHandoff = rememberDialerHandoff()

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

                    fun submitCasesCallOutcome(patientCase: PatientCase, input: CallOutcomeInput, attemptedAt: String?, report: (String?) -> Unit) {
                        scope.launch {
                            runCatching {
                                container.medtrackRepository.logCallOutcome(
                                    caseId = patientCase.id,
                                    taskId = input.taskId,
                                    reason = input.reason,
                                    outcome = input.outcome,
                                    note = input.note,
                                    attemptedAt = attemptedAt,
                                )
                            }.onSuccess { result ->
                                report(if (result.conflict) result.message else null)
                                refreshCaseList()
                                snackbarHostState.showSnackbar(result.message)
                            }.onFailure {
                                report(it.message ?: "Call logging failed")
                                snackbarHostState.showSnackbar(it.message ?: "Call logging failed")
                            }
                        }
                    }

                    LaunchedEffect(Unit) {
                        refreshCaseList()
                    }

                    CaseListScreen(
                        modifier = Modifier.fillMaxSize(),
                        cases = cases,
                        isRefreshing = isRefreshing,
                        pendingWriteCount = pendingWriteCount,
                        error = error,
                        onRefresh = { refreshCaseList() },
                        onCallPatient = { patientCase ->
                            dialerHandoff.startCall(context, patientCase) { message ->
                                scope.launch { snackbarHostState.showSnackbar(message) }
                            }
                        },
                        onOpenCase = { caseId -> navController.navigate(Routes.caseDetail(caseId)) },
                    )

                    DialerOutcomeSheet(dialerHandoff, container.medtrackRepository) { selectedCase, input, attemptedAt, report ->
                        submitCasesCallOutcome(selectedCase, input, attemptedAt, report)
                    }
                }
                composable(Routes.CASE_DETAIL) { entry ->
                    val cases by container.medtrackRepository.cases.collectAsState(initial = emptyList())
                    val caseId = entry.arguments?.getString("caseId").orEmpty()
                    val cachedCase by container.medtrackRepository.observeCase(caseId).collectAsState(initial = null)
                    val tasks by container.medtrackRepository.observeTasks(caseId).collectAsState(initial = emptyList())
                    val callLogs by container.medtrackRepository.observeCallLogs(caseId).collectAsState(initial = emptyList())
                    val vitals by container.medtrackRepository.observeVitals(caseId).collectAsState(initial = emptyList())
                    val vitalsThresholds by container.medtrackRepository.vitalsThresholds.collectAsState()
                    var caseActionMessage by remember { mutableStateOf<String?>(null) }
                    var caseError by remember { mutableStateOf<String?>(null) }
                    var caseRefreshing by remember { mutableStateOf(false) }
                    var timelineRevision by remember(caseId) { mutableStateOf(0) }
                    var hadPendingWrites by remember(caseId) { mutableStateOf(false) }
                    val dialerHandoff = rememberDialerHandoff(caseId)
                    val patientCase = cachedCase ?: cases.firstOrNull { it.id == caseId }
                    val defaultCaseScope = currentUserProfile.mobileDefaultCaseScope()
                    val caps = currentUserProfile?.capabilities.orEmpty()
                    val canEditCase = caps["case_edit"] ?: false
                    val canCreateTask = caps["task_create"] ?: false
                    val canEditTask = caps["task_edit"] ?: false
                    var taskMetadata by remember { mutableStateOf<TaskFormMetadata?>(null) }

                    LaunchedEffect(canCreateTask, canEditTask) {
                        if ((canCreateTask || canEditTask) && taskMetadata == null) {
                            runCatching { container.medtrackRepository.loadTaskFormMetadata() }
                                .onSuccess { taskMetadata = it }
                        }
                    }

                    fun refreshCaseDetail() {
                        if (caseId.isBlank()) return
                        timelineRevision += 1
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

                    fun submitCaseCallOutcome(patientCase: PatientCase, input: CallOutcomeInput, attemptedAt: String?, report: (String?) -> Unit) {
                        scope.launch {
                            runCatching {
                                container.medtrackRepository.logCallOutcome(
                                    caseId = patientCase.id,
                                    taskId = input.taskId,
                                    reason = input.reason,
                                    outcome = input.outcome,
                                    note = input.note,
                                    attemptedAt = attemptedAt,
                                )
                            }.onSuccess { result ->
                                report(if (result.conflict) result.message else null)
                                caseActionMessage = result.message
                                if (!result.queued) {
                                    refreshCaseDetail()
                                    runCatching {
                                        container.medtrackRepository.refreshCases(assignedTo = defaultCaseScope)
                                    }
                                }
                            }.onFailure {
                                report(it.message ?: "Call logging failed")
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

                    CaseDetailScreen(
                        loadRelatedCases = { cursor -> container.medtrackRepository.loadRelatedCases(caseId, cursor) },
                        onOpenRelatedCase = { id -> navController.navigate(Routes.caseDetail(id)) },
                        timelineRevision = timelineRevision,
                        loadTimeline = { filter, cursor -> container.medtrackRepository.loadCaseTimeline(caseId, filter, cursor) },
                        callLogs = callLogs,
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
                                        runCatching {
                                            container.medtrackRepository.refreshCases(assignedTo = defaultCaseScope)
                                        }
                                    }
                                }.onFailure {
                                    caseActionMessage = it.message ?: "Vitals save failed"
                                }
                            }
                        },
                        onCallPatient = { selectedCase ->
                            dialerHandoff.startCall(context, selectedCase) { caseActionMessage = it }
                        },
                        onMessagePatient = { selectedCase ->
                            caseActionMessage = if (openWhatsApp(context, selectedCase)) {
                                "Opening WhatsApp"
                            } else {
                                "No phone number on file"
                            }
                        },
                        onBack = { navController.popBackStack() },
                        canEditCase = canEditCase,
                        canCreateTask = canCreateTask,
                        canEditTask = canEditTask,
                        taskMetadata = taskMetadata,
                        onEditCase = {
                            navController.navigate(Routes.editCase(caseId)) { launchSingleTop = true }
                        },
                        onAncAction = { payload, report ->
                            scope.launch {
                                runCatching { container.medtrackRepository.recordAncAction(caseId, payload) }
                                    .onSuccess { message ->
                                        caseActionMessage = message
                                        timelineRevision += 1
                                        runCatching { container.medtrackRepository.refreshActiveCaseList() }
                                            .onFailure {
                                                if (it is CancellationException) throw it
                                                caseError = "ANC action saved. Refresh the inbox to update its list and counters."
                                            }
                                        report(null)
                                    }
                                    .onFailure {
                                        if (it is CancellationException) throw it
                                        report(it.message ?: "Could not record ANC action. Check connection or refresh the case.")
                                    }
                            }
                        },
                        onTaskAction = { action, taskId, report ->
                            scope.launch {
                                val outcome = when (action) {
                                    is TaskSheetAction.Create ->
                                        container.medtrackRepository.createTask(caseId, action.input)
                                    is TaskSheetAction.Edit ->
                                        if (taskId != null) {
                                            container.medtrackRepository.updateTask(taskId, caseId, action.input)
                                        } else {
                                            TaskWriteOutcome.Failure("Task is unavailable.")
                                        }
                                }
                                when (outcome) {
                                    is TaskWriteOutcome.Success -> {
                                        caseActionMessage = outcome.message
                                        refreshCaseDetail()
                                        runCatching {
                                            container.medtrackRepository.refreshCases(assignedTo = defaultCaseScope)
                                        }
                                        report(null)
                                    }
                                    is TaskWriteOutcome.ValidationError -> report(outcome.message)
                                    is TaskWriteOutcome.Failure -> report(outcome.message)
                                }
                            }
                        },
                        onEditVitals = { vitalId, input ->
                            scope.launch {
                                val outcome = container.medtrackRepository.updateVitals(
                                    vitalId = vitalId,
                                    caseId = caseId,
                                    bpSystolic = input.bpSystolic,
                                    bpDiastolic = input.bpDiastolic,
                                    pulse = input.pulse,
                                    spo2 = input.spo2,
                                    weightKg = input.weightKg,
                                    hemoglobin = input.hemoglobin,
                                )
                                caseActionMessage = when (outcome) {
                                    is VitalsWriteOutcome.Success -> {
                                        refreshCaseDetail()
                                        outcome.message
                                    }
                                    is VitalsWriteOutcome.ValidationError -> outcome.message
                                    is VitalsWriteOutcome.Failure -> outcome.message
                                }
                            }
                        },
                    )

                    DialerOutcomeSheet(dialerHandoff, container.medtrackRepository) { selectedCase, input, attemptedAt, report ->
                        submitCaseCallOutcome(selectedCase, input, attemptedAt, report)
                    }
                }
                composable(Routes.CREATE_CASE) { entry ->
                    val category = runCatching {
                        CaseCategory.valueOf(entry.arguments?.getString("category").orEmpty())
                    }.getOrDefault(CaseCategory.ANC)
                    CaseCreationScreen(
                        navigationBackHandler = { close -> BackHandler(onBack = close) },
                        modifier = Modifier.fillMaxSize(),
                        initialCategory = category,
                        loadMetadata = { container.medtrackRepository.loadCaseFormMetadata() },
                        searchPatients = { query -> container.medtrackRepository.searchPatients(query) },
                        submit = { input -> container.medtrackRepository.createCase(input) },
                        onBack = { navController.popBackStack() },
                        onCreated = { caseId, message ->
                            scope.launch {
                                snackbarHostState.showSnackbar(message)
                            }
                            navController.navigate(Routes.caseDetail(caseId.toString())) {
                                popUpTo(Routes.HOME) { inclusive = false }
                                launchSingleTop = true
                            }
                        },
                    )
                }
                composable(Routes.EDIT_CASE) { entry ->
                    val caseId = entry.arguments?.getString("caseId").orEmpty()
                    CaseEditScreen(
                        navigationBackHandler = { close -> BackHandler(onBack = close) },
                        modifier = Modifier.fillMaxSize(),
                        loadPrefill = { container.medtrackRepository.loadCaseEditForm(caseId) },
                        searchPatients = { query -> container.medtrackRepository.searchPatients(query) },
                        submit = { input -> container.medtrackRepository.updateCase(caseId, input) },
                        onBack = { navController.popBackStack() },
                        onSaved = { _, message ->
                            scope.launch { snackbarHostState.showSnackbar(message) }
                            navController.popBackStack()
                        },
                    )
                }
                composable(Routes.CALLS) {
                    val cases by container.medtrackRepository.cases.collectAsState(initial = emptyList())
                    var isRefreshing by remember { mutableStateOf(false) }
                    var error by remember { mutableStateOf<String?>(null) }
                    var actionMessage by remember { mutableStateOf<String?>(null) }
                    val dialerHandoff = rememberDialerHandoff()
                    var hadPendingWrites by remember { mutableStateOf(false) }

                    fun refreshCalls() {
                        scope.launch {
                            isRefreshing = true
                            error = null
                            runCatching {
                                container.medtrackRepository.refreshCases(
                                    bucket = "all",
                                    assignedTo = "all",
                                    scopeContext = "calls",
                                )
                            }.onFailure {
                                error = it.message ?: "Unable to refresh calls"
                            }
                            isRefreshing = false
                        }
                    }

                    fun submitCallOutcome(patientCase: PatientCase, input: CallOutcomeInput, attemptedAt: String?, report: (String?) -> Unit) {
                        scope.launch {
                            runCatching {
                                container.medtrackRepository.logCallOutcome(
                                    caseId = patientCase.id,
                                    taskId = input.taskId,
                                    reason = input.reason,
                                    outcome = input.outcome,
                                    note = input.note,
                                    attemptedAt = attemptedAt,
                                )
                            }.onSuccess { result ->
                                report(if (result.conflict) result.message else null)
                                actionMessage = result.message
                                refreshCalls()
                            }.onFailure {
                                report(it.message ?: "Call logging failed")
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

                    CallsScreen(
                        modifier = Modifier.fillMaxSize(),
                        cases = cases,
                        isRefreshing = isRefreshing,
                        error = error,
                        actionMessage = actionMessage,
                        onRefresh = { refreshCalls() },
                        onOpenCase = { caseId -> navController.navigate(Routes.caseDetail(caseId)) },
                        onCallPatient = { patientCase ->
                            dialerHandoff.startCall(context, patientCase) { actionMessage = it }
                        },
                        onMessagePatient = { patientCase ->
                            actionMessage = if (openWhatsApp(context, patientCase)) {
                                "Opening WhatsApp"
                            } else {
                                "Unable to open WhatsApp"
                            }
                        },
                    )

                    DialerOutcomeSheet(dialerHandoff, container.medtrackRepository) { selectedCase, input, attemptedAt, report ->
                        submitCallOutcome(selectedCase, input, attemptedAt, report)
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
                            runCatching { container.medtrackRepository.refreshNotifications(notificationsFilterType) }
                                .onFailure { error = it.message ?: "Unable to refresh notifications" }
                            isRefreshing = false
                        }
                    }

                    LaunchedEffect(notificationsFilterType) {
                        refreshNotifications()
                    }

                    NotificationsScreen(
                        modifier = Modifier.fillMaxSize(),
                        notifications = notifications,
                        isRefreshing = isRefreshing,
                        error = error,
                        filterType = notificationsFilterType,
                        onRefresh = { refreshNotifications() },
                        onOpenNotification = { item ->
                            scope.launch {
                                runCatching { container.medtrackRepository.markNotificationRead(item.id) }
                                navController.navigate(Routes.alertDetail(item.id))
                            }
                        },
                    )
                }
                composable(Routes.ALERT_DETAIL) { entry ->
                    val notificationId = Uri.decode(entry.arguments?.getString("notificationId").orEmpty())
                    val notifications by container.medtrackRepository.notifications.collectAsState(initial = emptyList())
                    val cases by container.medtrackRepository.cases.collectAsState(initial = emptyList())
                    val notification = notifications.firstOrNull { it.id == notificationId }
                    val patientCase = notification?.resolvePatientCase(cases)
                    val dialerHandoff = rememberDialerHandoff()

                    LaunchedEffect(notification?.caseId, patientCase?.id) {
                        val caseId = notification?.caseId?.takeIf { it.isNotBlank() }
                        if (caseId != null && patientCase == null) {
                            runCatching { container.medtrackRepository.refreshCaseDetail(caseId) }
                        }
                    }

                    fun submitAlertCallOutcome(selectedCase: PatientCase, input: CallOutcomeInput, attemptedAt: String?, report: (String?) -> Unit) {
                        scope.launch {
                            runCatching {
                                container.medtrackRepository.logCallOutcome(
                                    caseId = selectedCase.id,
                                    taskId = input.taskId,
                                    reason = input.reason,
                                    outcome = input.outcome,
                                    note = input.note,
                                    attemptedAt = attemptedAt,
                                )
                            }.onSuccess { result ->
                                report(if (result.conflict) result.message else null)
                                snackbarHostState.showSnackbar(result.message)
                                if (!result.queued) {
                                    runCatching { container.medtrackRepository.refreshCaseDetail(selectedCase.id) }
                                }
                            }.onFailure {
                                report(it.message ?: "Call logging failed")
                                snackbarHostState.showSnackbar(it.message ?: "Call logging failed")
                            }
                        }
                    }

                    AlertDetailScreen(
                        modifier = Modifier.fillMaxSize(),
                        notification = notification,
                        patientCase = patientCase,
                        onBack = { navController.popBackStack() },
                        onCallPatient = { selectedCase ->
                            dialerHandoff.startCall(context, selectedCase) { message ->
                                scope.launch { snackbarHostState.showSnackbar(message) }
                            }
                        },
                        onOpenCase = { caseId ->
                            navController.navigate(Routes.caseDetail(caseId))
                        },
                    )

                    DialerOutcomeSheet(dialerHandoff, container.medtrackRepository) { selectedCase, input, attemptedAt, report ->
                        submitAlertCallOutcome(selectedCase, input, attemptedAt, report)
                    }
                }
                composable(Routes.STAFF_TOOLS) { entry ->
                    StaffToolsScreen(
                        repository = container.staffToolsRepository,
                        onBack = { navController.popBackStack() },
                        initialTab = entry.arguments?.getString("tab")?.toIntOrNull() ?: 0,
                    )
                }
                composable(Routes.ME) {
                    LaunchedEffect(Unit) {
                        if (currentUserProfile == null) {
                            runCatching {
                                setCurrentUser(container.authRepository.currentUser())
                            }
                        }
                    }
                    ProfileScreen(
                        modifier = Modifier.fillMaxSize(),
                        displayName = currentUserDisplayName ?: "MEDTRACK user",
                        roleLabel = currentUserProfile.roleLabel(),
                        buildLabel = "MEDTRACK ${BuildConfig.VERSION_NAME} \u00B7 code ${BuildConfig.VERSION_CODE}",
                        pendingWriteCount = pendingWriteCount,
                        unreadNotificationCount = shellNotifications.count { !it.isRead },
                        redFlagUnreadCount = shellNotifications.count { it.type == "red_flag" && !it.isRead },
                        assignmentUnreadCount = shellNotifications.count { it.type == "assignment" && !it.isRead },
                        overdueUnreadCount = shellNotifications.count { it.type == "overdue" && !it.isRead },
                        onOpenNotifications = { type ->
                            notificationsFilterType = type
                            navController.navigate(Routes.NOTIFICATIONS)
                        },
                        onSignOut = { signOut() },
                        onOpenStaffTools = if (staffSession != null) ({ navController.navigate("staff_tools/0") }) else null,
                    )
                }
            }

            if (showBottomNav) {
                MedtrackBottomBar(
                    modifier = Modifier.align(Alignment.BottomCenter),
                    // Notifications is a sub-page of the Me tab, so keep Me highlighted there.
                    currentRoute = if (currentRoute == Routes.NOTIFICATIONS) Routes.ME else currentRoute,
                    unreadCount = shellNotifications.count { !it.isRead },
                    // Hide the quick-add (+) until the profile confirms case_create, so we
                    // never surface an action the server will reject.
                    canQuickAdd = currentUserProfile?.capabilities?.get("case_create") ?: false,
                    onNavigate = { route ->
                        // The Me tab always returns to its root: never restore the
                        // Notifications sub-page on top of it (otherwise tapping Me from
                        // within Notifications would just re-open Notifications).
                        if (route == Routes.ME) {
                            navController.navigate(Routes.ME) {
                                launchSingleTop = true
                                restoreState = false
                                popUpTo(navController.graph.findStartDestination().id) {
                                    saveState = true
                                }
                            }
                        } else {
                            navigateTopLevel(route)
                        }
                    },
                    onQuickAdd = { showQuickAddSheet = true },
                )
            }
            }
        }

        if (showQuickAddSheet && showBottomNav) {
            QuickAddSheet(
                categoryOptions = shellCategoryOptions,
                onDismiss = { showQuickAddSheet = false },
                onCreateCase = { pathway ->
                    showQuickAddSheet = false
                    navController.navigate(Routes.createCase(pathway.category, pathway.label))
                },
                onOpenHomeSearch = { query ->
                    showQuickAddSheet = false
                    homeSearchQuery = query
                    navigateTopLevel(Routes.HOME)
                },
            )
        }

        syncConflicts.firstOrNull()?.takeIf {
            currentDestination?.route !in setOf(Routes.LOGIN, Routes.LOCK_SETUP, Routes.UNLOCK)
        }?.let { conflict ->
            val conflictCase = cachedCases.firstOrNull { it.id == conflict.caseId }
            AlertDialog(
                onDismissRequest = { /* Recovery items remain until an explicit action. */ },
                title = { Text(conflict.failureTitle()) },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(
                            text = conflict.caseLabel(conflictCase),
                            color = MedtrackColors.Ink,
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            text = conflict.message.ifBlank { "Server version was kept for an offline change." },
                            color = MedtrackColors.Muted,
                        )
                        conflict.httpStatus?.let { status ->
                            Text(
                                text = "Server response $status · original change retained",
                                color = MedtrackColors.Faint,
                                style = MaterialTheme.typography.labelSmall,
                            )
                        }
                        Surface(
                            shape = RoundedCornerShape(12.dp),
                            color = MedtrackColors.WarningSoft,
                            border = BorderStroke(1.dp, MedtrackColors.Warning.copy(alpha = 0.22f)),
                        ) {
                            Text(
                                text = "${conflict.fieldLabel()}: ${conflict.localChangeLabel()} -> server kept",
                                color = MedtrackColors.Warning,
                                style = MaterialTheme.typography.bodySmall,
                                fontWeight = FontWeight.SemiBold,
                                modifier = Modifier.padding(10.dp),
                            )
                        }
                        conflict.caseId?.let { caseId ->
                            TextButton(
                                onClick = {
                                    navController.navigate(Routes.caseDetail(caseId)) {
                                        launchSingleTop = true
                                    }
                                },
                            ) {
                                Text("Review server record")
                            }
                        }
                    }
                },
                confirmButton = {
                    TextButton(
                        onClick = {
                            scope.launch {
                                runCatching {
                                    container.medtrackRepository.retrySyncConflict(conflict.clientWriteId)
                                }.onFailure { error ->
                                    snackbarHostState.showSnackbar(error.message ?: "Unable to retry the original change")
                                }
                            }
                        },
                    ) {
                        Text("Retry original")
                    }
                },
                dismissButton = {
                    TextButton(
                        onClick = {
                            scope.launch { container.medtrackRepository.discardSyncConflict(conflict.clientWriteId) }
                        },
                    ) {
                        Text("Discard local change")
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
    canQuickAdd: Boolean,
    onNavigate: (String) -> Unit,
    onQuickAdd: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .fillMaxWidth()
            .height(BottomNavScale.ShellHeight),
    ) {
        Surface(
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .fillMaxWidth()
                .padding(horizontal = BottomNavScale.BarHorizontalInset)
                .padding(bottom = BottomNavScale.BarBottomInset)
                .height(BottomNavScale.BarHeight),
            shape = RoundedCornerShape(BottomNavScale.BarCornerRadius),
            // Near-opaque so list rows slide cleanly underneath without text bleeding
            // through, while a hint of translucency keeps the floating-glass feel.
            color = MedtrackColors.Card.copy(alpha = 0.98f),
            border = BorderStroke(BottomNavScale.BarBorderWidth, Color.White.copy(alpha = 0.6f)),
            shadowElevation = MedtrackElevation.Pop,
        ) {
            Row(
                modifier = Modifier.fillMaxSize(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                BottomNavItem(bottomDestinations[0], currentRoute, onNavigate)
                BottomNavItem(bottomDestinations[1], currentRoute, onNavigate)
                BottomNavCenter(canQuickAdd = canQuickAdd, onQuickAdd = onQuickAdd)
                BottomNavItem(bottomDestinations[2], currentRoute, onNavigate)
                BottomNavItem(
                    destination = bottomDestinations[3],
                    currentRoute = currentRoute,
                    onNavigate = onNavigate,
                    badge = unreadCount.takeIf { it > 0 }?.coerceAtMost(99)?.toString(),
                )
            }
        }
    }
}

@Composable
private fun RowScope.BottomNavCenter(
    canQuickAdd: Boolean,
    onQuickAdd: () -> Unit,
) {
    Box(
        modifier = Modifier
            .width(BottomNavScale.CenterColumnWidth)
            .fillMaxHeight(),
        contentAlignment = Alignment.Center,
    ) {
        if (canQuickAdd) {
            Surface(
                modifier = Modifier.size(BottomNavScale.CenterButtonSize),
                shape = RoundedCornerShape(BottomNavScale.CenterButtonRadius),
                color = Color.Transparent,
                shadowElevation = MedtrackElevation.Fab,
            ) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(
                            brush = Brush.linearGradient(
                                listOf(
                                    MedtrackColors.Primary,
                                    MedtrackColors.PrimaryDark,
                                    MedtrackColors.PrimaryDeep,
                                ),
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
}

@Composable
private fun RowScope.BottomNavItem(
    destination: BottomDestination,
    currentRoute: String?,
    onNavigate: (String) -> Unit,
    badge: String? = null,
) {
    val selected = currentRoute == destination.route
    val color = if (selected) MedtrackColors.Primary else MedtrackColors.Faint

    Box(
        modifier = Modifier
            .weight(1f)
            .fillMaxHeight()
            .clickable { onNavigate(destination.route) },
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            // Reserved dot slot keeps every tab the same height; only the
            // selected tab fills it, marking the active destination above the icon.
            Box(
                modifier = Modifier.size(BottomNavScale.ItemDotSize),
            ) {
                if (selected) {
                    Box(
                        modifier = Modifier
                            .fillMaxSize()
                            .background(MedtrackColors.Primary, CircleShape),
                    )
                }
            }
            Spacer(modifier = Modifier.height(BottomNavScale.ItemDotTopGap))
            Box(
                modifier = Modifier.size(BottomNavScale.ItemIconBoxSize),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    imageVector = if (selected) destination.selectedIcon else destination.icon,
                    contentDescription = destination.label,
                    modifier = Modifier.size(BottomNavScale.ItemIconSize),
                    tint = color,
                )
                badge?.let {
                    Surface(
                        modifier = Modifier
                            .align(Alignment.TopEnd)
                            .offset(x = 5.dp, y = (-5).dp),
                        shape = CircleShape,
                        color = MedtrackColors.Danger,
                        border = BorderStroke(1.5.dp, MedtrackColors.Card),
                    ) {
                        Text(
                            text = it,
                            color = Color.White,
                            style = MaterialTheme.typography.labelSmall.copy(fontSize = 9.sp),
                            fontWeight = FontWeight.ExtraBold,
                            maxLines = 1,
                            modifier = Modifier.padding(horizontal = 5.dp, vertical = 1.dp),
                        )
                    }
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
    categoryOptions: List<CategoryFilterOption>,
    onDismiss: () -> Unit,
    onCreateCase: (QuickAddPathwaySpec) -> Unit,
    onOpenHomeSearch: (String) -> Unit,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val pathways = categoryOptions.quickAddPathways()
    var searchQuery by remember { mutableStateOf("") }
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = Color.White,
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
                        text = "Search for a patient, or start a new case.",
                        color = MedtrackColors.Muted,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
                MedtrackIconBadge(icon = Icons.Outlined.HealthAndSafety, tint = MedtrackColors.Primary)
            }

            QuickAddSearchBar(
                value = searchQuery,
                onValueChange = { searchQuery = it },
                onSearch = { onOpenHomeSearch(searchQuery) },
            )

            MedtrackSectionTitle(title = "Start a new case")
            Column(verticalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                pathways.forEach { pathway ->
                    QuickAddPathway(
                        pathway = pathway,
                        onClick = { onCreateCase(pathway) },
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
        }
    }
}

@Composable
private fun QuickAddSearchBar(
    value: String,
    onValueChange: (String) -> Unit,
    onSearch: () -> Unit,
) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .height(54.dp),
        shape = RoundedCornerShape(18.dp),
        color = MedtrackColors.Card,
        border = BorderStroke(1.dp, MedtrackColors.Border),
    ) {
        Row(
            modifier = Modifier.padding(start = 14.dp, end = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(9.dp),
        ) {
            Icon(
                imageVector = Icons.Outlined.Search,
                contentDescription = null,
                tint = MedtrackColors.Primary,
                modifier = Modifier.size(20.dp),
            )
            Box(modifier = Modifier.weight(1f)) {
                BasicTextField(
                    value = value,
                    onValueChange = onValueChange,
                    textStyle = MaterialTheme.typography.bodyMedium.copy(color = MedtrackColors.Ink),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                if (value.isBlank()) {
                    Text(
                        text = "Search name, MTNO, UHID, phone",
                        color = MedtrackColors.Muted,
                        style = MaterialTheme.typography.bodyMedium,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
            TextButton(onClick = onSearch) {
                Text("Search")
            }
        }
    }
}

@Composable
private fun QuickAddPathway(
    pathway: QuickAddPathwaySpec,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val color = pathway.color
    Surface(
        modifier = modifier.clickable(onClick = onClick),
        shape = RoundedCornerShape(16.dp),
        color = MedtrackColors.Card,
        border = BorderStroke(1.dp, MedtrackColors.Border),
    ) {
        Row(
            modifier = Modifier.padding(start = 12.dp, end = 12.dp, top = 12.dp, bottom = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Surface(
                modifier = Modifier.size(46.dp),
                shape = RoundedCornerShape(13.dp),
                color = color.copy(alpha = 0.14f),
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(
                        painter = painterResource(pathway.iconResId),
                        contentDescription = null,
                        tint = color,
                        modifier = Modifier.size(24.dp),
                    )
                }
            }
            Column(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(2.dp),
            ) {
                Text(
                    text = pathway.label,
                    color = MedtrackColors.Ink,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.ExtraBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = pathway.description,
                    color = MedtrackColors.Muted,
                    style = MaterialTheme.typography.labelMedium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Icon(
                imageVector = Icons.Outlined.ChevronRight,
                contentDescription = null,
                tint = color,
                modifier = Modifier.size(22.dp),
            )
        }
    }
}

@Composable
private fun ProfileScreen(
    displayName: String,
    roleLabel: String,
    buildLabel: String,
    pendingWriteCount: Int,
    unreadNotificationCount: Int,
    redFlagUnreadCount: Int,
    assignmentUnreadCount: Int,
    overdueUnreadCount: Int,
    onOpenNotifications: (String?) -> Unit,
    onSignOut: () -> Unit,
    onOpenStaffTools: (() -> Unit)?,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .background(MedtrackColors.Surface)
            .verticalScroll(rememberScrollState())
            // Reserve space so the last row clears the floating bottom nav overlay.
            .padding(start = 12.dp, end = 12.dp, top = 10.dp, bottom = BottomNavScale.ShellHeight + 16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Surface(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(20.dp),
            color = Color.Transparent,
            shadowElevation = 8.dp,
        ) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(
                        Brush.linearGradient(
                            listOf(MedtrackColors.Primary, MedtrackColors.PrimaryDark, MedtrackColors.PrimaryDeep),
                        ),
                    )
                    .padding(18.dp),
            ) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Surface(shape = RoundedCornerShape(16.dp), color = Color.White.copy(alpha = 0.18f), modifier = Modifier.size(54.dp)) {
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
                            text = "$roleLabel · MEDTRACK mobile",
                            color = Color.White.copy(alpha = 0.82f),
                            style = MaterialTheme.typography.bodySmall,
                            fontWeight = FontWeight.SemiBold,
                        )
                    }
                }
            }
        }

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            ProfileStatCard(
                label = "Pending sync",
                value = pendingWriteCount.toString(),
                color = if (pendingWriteCount > 0) MedtrackColors.Warning else MedtrackColors.Success,
                background = if (pendingWriteCount > 0) MedtrackColors.WarningSoft else MedtrackColors.SuccessSoft,
                icon = Icons.Outlined.CloudDone,
                modifier = Modifier.weight(1f),
            )
            ProfileStatCard(
                label = "Unread alerts",
                value = unreadNotificationCount.toString(),
                color = if (unreadNotificationCount > 0) MedtrackColors.Danger else MedtrackColors.Muted,
                background = if (unreadNotificationCount > 0) MedtrackColors.DangerSoft else MedtrackColors.SurfaceAlt,
                icon = Icons.Outlined.ErrorOutline,
                modifier = Modifier.weight(1f),
            )
        }

        if (onOpenStaffTools != null) {
            OutlinedButton(onClick = onOpenStaffTools, modifier = Modifier.fillMaxWidth()) { Text("Staff tools") }
        }

        Text(
            text = "NOTIFICATIONS",
            color = MedtrackColors.Faint,
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.ExtraBold,
            letterSpacing = 0.5.sp,
            modifier = Modifier.padding(start = 2.dp),
        )
        NotificationCategoryRow(
            title = "Red flags",
            subtitle = "Patients flagged for urgent review",
            icon = Icons.Outlined.ErrorOutline,
            accent = MedtrackColors.Danger,
            unreadCount = redFlagUnreadCount,
            onClick = { onOpenNotifications("red_flag") },
        )
        NotificationCategoryRow(
            title = "Assignments",
            subtitle = "Cases newly assigned to you",
            icon = Icons.Outlined.AssignmentInd,
            accent = MedtrackColors.Primary,
            unreadCount = assignmentUnreadCount,
            onClick = { onOpenNotifications("assignment") },
        )
        NotificationCategoryRow(
            title = "Overdue tasks",
            subtitle = "Tasks past their due date",
            icon = Icons.Outlined.Schedule,
            accent = MedtrackColors.Warning,
            unreadCount = overdueUnreadCount,
            onClick = { onOpenNotifications("overdue") },
        )
        NotificationCategoryRow(
            title = "All notifications",
            subtitle = "Everything in one place",
            icon = Icons.Outlined.Notifications,
            accent = MedtrackColors.Muted,
            unreadCount = unreadNotificationCount,
            onClick = { onOpenNotifications(null) },
        )

        Button(
            onClick = onSignOut,
            modifier = Modifier
                .fillMaxWidth()
                .height(52.dp),
            shape = RoundedCornerShape(15.dp),
            colors = ButtonDefaults.buttonColors(containerColor = MedtrackColors.Ink),
        ) {
            Icon(imageVector = Icons.Outlined.Lock, contentDescription = null, modifier = Modifier.size(19.dp))
            Spacer(modifier = Modifier.width(8.dp))
            Text("Sign out", fontWeight = FontWeight.ExtraBold)
        }
        Text(
            text = buildLabel.replace("code", "build"),
            color = MedtrackColors.Faint,
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.align(Alignment.CenterHorizontally),
        )
    }
}

@Composable
private fun ProfileStatCard(
    label: String,
    value: String,
    color: Color,
    background: Color,
    icon: ImageVector,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(16.dp),
        color = MedtrackColors.Card,
        border = BorderStroke(1.dp, MedtrackColors.Border),
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(9.dp),
        ) {
            Surface(shape = RoundedCornerShape(10.dp), color = background, modifier = Modifier.size(34.dp)) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(imageVector = icon, contentDescription = null, tint = color, modifier = Modifier.size(18.dp))
                }
            }
            Text(
                text = value,
                color = MedtrackColors.Ink,
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.ExtraBold,
                maxLines = 1,
            )
            Text(
                text = label,
                color = MedtrackColors.Muted,
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
            )
        }
    }
}

@Composable
private fun NotificationCategoryRow(
    title: String,
    subtitle: String,
    icon: ImageVector,
    accent: Color,
    unreadCount: Int,
    onClick: () -> Unit,
) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        shape = RoundedCornerShape(16.dp),
        color = MedtrackColors.Card,
        border = BorderStroke(1.dp, MedtrackColors.Border),
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 13.dp),
            horizontalArrangement = Arrangement.spacedBy(13.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Surface(shape = RoundedCornerShape(11.dp), color = accent.copy(alpha = 0.14f), modifier = Modifier.size(38.dp)) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(imageVector = icon, contentDescription = null, tint = accent, modifier = Modifier.size(19.dp))
                }
            }
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(title, fontWeight = FontWeight.Bold, color = MedtrackColors.Ink, maxLines = 1)
                Text(subtitle, color = MedtrackColors.Muted, style = MaterialTheme.typography.bodySmall, maxLines = 1)
            }
            if (unreadCount > 0) {
                Surface(
                    shape = CircleShape,
                    color = accent,
                ) {
                    Text(
                        text = unreadCount.coerceAtMost(99).toString(),
                        color = Color.White,
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.ExtraBold,
                        maxLines = 1,
                        modifier = Modifier.padding(horizontal = 7.dp, vertical = 2.dp),
                    )
                }
            }
            Icon(imageVector = Icons.Outlined.ChevronRight, contentDescription = null, tint = MedtrackColors.Faint, modifier = Modifier.size(20.dp))
        }
    }
}

private data class QuickAddPathwaySpec(
    val label: String,
    val color: Color,
    val category: CaseCategory,
    val iconResId: Int,
    val description: String,
)

private fun List<CategoryFilterOption>.quickAddPathways(): List<QuickAddPathwaySpec> {
    val supportedCategories = setOf(CaseCategory.ANC, CaseCategory.MEDICINE, CaseCategory.SURGERY)
    val fromServer = filter { it.category in supportedCategories }
        .distinctBy { it.category.name }
        .map { option ->
            QuickAddPathwaySpec(
                label = option.label,
                color = categoryColor(option.category),
                category = option.category,
                iconResId = option.category.quickAddIconResId(),
                description = option.quickAddDescription(),
            )
        }
    val byKey = (fromServer + defaultQuickAddPathways())
        .distinctBy { it.category.name }
        .associateBy { it.category.name }
    return listOfNotNull(
        byKey[CaseCategory.ANC.name],
        byKey[CaseCategory.MEDICINE.name],
        byKey[CaseCategory.SURGERY.name],
    )
}

private fun defaultQuickAddPathways(): List<QuickAddPathwaySpec> =
    listOf(
        QuickAddPathwaySpec("ANC", MedtrackColors.Anc, CaseCategory.ANC, CaseCategory.ANC.quickAddIconResId(), "Antenatal follow-up"),
        QuickAddPathwaySpec("Medicine", MedtrackColors.Medicine, CaseCategory.MEDICINE, CaseCategory.MEDICINE.quickAddIconResId(), "General medicine"),
        QuickAddPathwaySpec("Surgery", MedtrackColors.Surgery, CaseCategory.SURGERY, CaseCategory.SURGERY.quickAddIconResId(), "Pre/post-op review"),
    )

private fun CaseCategory.quickAddIconResId(): Int =
    when (this) {
        CaseCategory.ANC -> DesignR.drawable.ic_cat_anc
        CaseCategory.SURGERY -> DesignR.drawable.ic_cat_surgery
        CaseCategory.MEDICINE -> DesignR.drawable.ic_cat_medicine
        else -> DesignR.drawable.ic_cat_medicine
    }

private fun CategoryFilterOption.quickAddDescription(): String =
    when (category) {
        CaseCategory.ANC -> "Antenatal follow-up"
        CaseCategory.SURGERY -> "Pre/post-op review"
        CaseCategory.MEDICINE -> "General medicine"
        else -> "Custom pathway"
    }

private fun UserProfileDto?.roleLabel(): String =
    this?.roles
        ?.filter { it.isNotBlank() }
        ?.joinToString(" / ")
        ?.takeIf { it.isNotBlank() }
        ?: "Role unavailable"

private fun SyncConflict.caseLabel(patientCase: PatientCase?): String =
    patientCase?.patientName
        ?: caseId?.takeIf { it.isNotBlank() }?.let { "Case $it" }
        ?: "Unknown case"

private fun SyncConflict.fieldLabel(): String =
    when (writeType) {
        PendingWriteTypes.TASK_COMPLETE -> "Task status"
        PendingWriteTypes.CALL_OUTCOME -> "Call outcome"
        PendingWriteTypes.VITALS_CREATE -> "Vitals"
        else -> "Offline write"
    }

private fun SyncConflict.localChangeLabel(): String =
    when (writeType) {
        PendingWriteTypes.TASK_COMPLETE -> "local completed"
        PendingWriteTypes.CALL_OUTCOME -> "local call note"
        PendingWriteTypes.VITALS_CREATE -> "local vitals"
        else -> "local change"
    }

private fun SyncConflict.failureTitle(): String =
    when (failureKind) {
        "AUTHENTICATION" -> "Sign in to finish syncing"
        "VALIDATION" -> "Change needs attention"
        "MALFORMED" -> "Saved change cannot be read"
        else -> "Sync conflict"
    }

private fun categoryColor(category: CaseCategory): Color =
    when (category) {
        CaseCategory.ANC -> MedtrackColors.Anc
        CaseCategory.SURGERY -> MedtrackColors.Surgery
        CaseCategory.MEDICINE -> MedtrackColors.Medicine
        CaseCategory.OTHER -> MedtrackColors.Primary
    }

private fun NotificationItem.resolvePatientCase(cases: List<PatientCase>): PatientCase? {
    val exactCaseId = caseId?.trim()?.takeIf { it.isNotBlank() }
    if (exactCaseId != null) {
        cases.firstOrNull { it.id == exactCaseId }?.let { return it }
    }

    val bodyPatientName = body.substringBefore(":").trim().takeIf { it.isNotBlank() && it != body.trim() }
    if (bodyPatientName != null) {
        cases.firstOrNull { it.patientName.equals(bodyPatientName, ignoreCase = true) }?.let { return it }
    }

    return cases.firstOrNull { patientCase ->
        body.contains(patientCase.patientName, ignoreCase = true) ||
            title.contains(patientCase.patientName, ignoreCase = true)
    }
}

private fun String.initials(): String {
    val parts = trim().split(Regex("\\s+")).filter { it.isNotBlank() }
    return parts.take(2).joinToString("") { it.take(1).uppercase(Locale.getDefault()) }.ifBlank { "M" }
}

private class DialerHandoff {
    var pendingCase by mutableStateOf<PatientCase?>(null)
    var startedAt by mutableStateOf<Long?>(null)
    var leftForDialer by mutableStateOf(false)
    var outcomeCase by mutableStateOf<PatientCase?>(null)
    var outcomeAttemptedAt by mutableStateOf<String?>(null)

    fun clearDialing() {
        pendingCase = null
        startedAt = null
        leftForDialer = false
    }

    fun clearOutcome() {
        outcomeCase = null
        outcomeAttemptedAt = null
    }
}

/**
 * Shared dialer hand-off used by Home, Cases, Case detail, and Calls. It tracks the case that was
 * dialed, detects the return from the system dialer via the lifecycle, and surfaces the case that
 * needs a call-outcome prompt. [key] lets callers reset the state per case (e.g. the case detail).
 */
@Composable
private fun rememberDialerHandoff(key: Any? = Unit): DialerHandoff {
    val handoff = remember(key) { DialerHandoff() }
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner, handoff.pendingCase) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_STOP -> {
                    if (handoff.pendingCase != null) {
                        handoff.leftForDialer = true
                    }
                }
                Lifecycle.Event.ON_START -> {
                    val startedAt = handoff.startedAt
                    val returnedFromDialer = handoff.pendingCase != null &&
                        handoff.leftForDialer &&
                        startedAt != null &&
                        System.currentTimeMillis() - startedAt > 300L
                    if (returnedFromDialer) {
                        handoff.outcomeCase = handoff.pendingCase
                        handoff.outcomeAttemptedAt = startedAt?.let(::utcTimestampFromMillis)
                        handoff.clearDialing()
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
    return handoff
}

/** Opens the dialer for [patientCase], reporting a human-readable reason through [onFailure]. */
private fun DialerHandoff.startCall(
    context: Context,
    patientCase: PatientCase,
    onFailure: (String) -> Unit,
) {
    if (patientCase.phoneNumber.isNullOrBlank()) {
        onFailure("No phone number on file")
        return
    }
    pendingCase = patientCase
    startedAt = System.currentTimeMillis()
    leftForDialer = false
    if (!openDialer(context, patientCase)) {
        clearDialing()
        outcomeAttemptedAt = null
        onFailure("Unable to open dialer")
    }
}

/** Renders the call-outcome sheet when the handoff has a case awaiting an outcome. */
@Composable
private fun DialerOutcomeSheet(
    handoff: DialerHandoff,
    repository: MedtrackRepository,
    onSubmit: (PatientCase, CallOutcomeInput, String?, (String?) -> Unit) -> Unit,
) {
    val patientCase = handoff.outcomeCase ?: return
    val tasks by remember(repository, patientCase.id) { repository.observeTasks(patientCase.id) }
        .collectAsState(initial = emptyList())
    LaunchedEffect(patientCase.id) { runCatching { repository.refreshCaseDetail(patientCase.id) } }
    val choices = tasks.map { CallTaskChoice(it.id, it.title) }.toMutableList()
    patientCase.nextTaskId?.let { id ->
        if (choices.none { it.id == id }) choices.add(CallTaskChoice(id, patientCase.nextTaskTitle ?: "Selected task"))
    }
    CallOutcomeSheet(
        patientName = patientCase.patientName,
        tasks = choices,
        initialTaskId = patientCase.nextTaskId,
        onDismiss = { handoff.clearOutcome() },
        onSubmit = { input, report ->
            onSubmit(patientCase, input, handoff.outcomeAttemptedAt) { error ->
                report(error)
                if (error == null) handoff.clearOutcome()
            }
        },
    )
}

private fun openDialer(context: android.content.Context, patientCase: PatientCase): Boolean {
    val number = patientCase.phoneNumber?.takeIf { it.isNotBlank() } ?: return false
    val intent = Intent(Intent.ACTION_DIAL).apply {
        data = "tel:$number".toUri()
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
        data = "https://wa.me/$number".toUri()
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
