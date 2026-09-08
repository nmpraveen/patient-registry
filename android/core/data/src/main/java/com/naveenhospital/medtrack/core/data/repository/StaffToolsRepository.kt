package com.naveenhospital.medtrack.core.data.repository

import com.naveenhospital.medtrack.core.data.auth.AccountSessionIdentity
import com.naveenhospital.medtrack.core.domain.model.*
import com.naveenhospital.medtrack.core.network.api.StaffOperationsApi
import com.naveenhospital.medtrack.core.network.model.*
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import retrofit2.HttpException

sealed interface StaffContent {
    data class Directory(val rows: List<DirectoryContact>, val hasNext: Boolean) : StaffContent
    data class Contact(val row: DirectoryContact) : StaffContent
    data class Announcements(val rows: List<StaffAnnouncement>, val hasNext: Boolean, val clock: StaffServerClock?) : StaffContent
    data class Announcement(val row: StaffAnnouncement, val clock: StaffServerClock) : StaffContent
    data class Reminders(val rows: List<ReminderOccurrenceDto>, val hasNext: Boolean, val today: String?) : StaffContent
    data class Reminder(val definition: StaffReminderDto, val history: List<ReminderOccurrenceDto>, val hasNext: Boolean) : StaffContent
    data class Assignees(val definition: StaffReminderDto, val rows: List<StaffPersonDto>, val hasNext: Boolean) : StaffContent
}

data class StaffScreenState(
    val loading: Boolean = false,
    val content: StaffContent? = null,
    val error: String? = null,
)

/** Fresh online reads only: no clinical cache, encrypted outbox or notification writes. */
class StaffToolsRepository(
    private val apiForSession: (AccountSessionIdentity) -> StaffOperationsApi,
    private val sessionIsCurrent: (AccountSessionIdentity) -> Boolean,
    private val monotonicMillis: () -> Long,
) {
    private val session = MutableStateFlow<AccountSessionIdentity?>(null)
    val activeSession: StateFlow<AccountSessionIdentity?> = session
    private val screenStore = StaffSessionState(StaffScreenState())
    val screen = screenStore.state
    private val bannerStore = StaffSessionState<List<StaffAnnouncement>>(emptyList())
    val announcements = bannerStore.state
    private val noticeStore = StaffSessionState(0)
    val dueReminderCount = noticeStore.state
    private var serverClock: StaffServerClock? = null
    private var activeApi: StaffOperationsApi? = null

    @Synchronized
    fun activate(identity: AccountSessionIdentity?) {
        screenStore.activate(identity)
        bannerStore.activate(identity)
        noticeStore.activate(identity)
        serverClock = null
        activeApi = identity?.let(apiForSession)
        session.value = identity
    }

    @Synchronized
    fun clearScreen() {
        screenStore.activate(session.value)
    }

    private fun requireSession(): AccountSessionIdentity = session.value
        ?.takeIf { sessionIsCurrent(it) && screenStore.isCurrent(it) }
        ?: throw CancellationException("Staff session changed")

    private fun checkSession(identity: AccountSessionIdentity) {
        if (session.value != identity || !sessionIsCurrent(identity)) {
            throw CancellationException("Staff session changed")
        }
    }

    @Synchronized
    private fun api(identity: AccountSessionIdentity): StaffOperationsApi {
        checkSession(identity)
        return activeApi ?: throw CancellationException("Staff session changed")
    }

    private suspend fun load(block: suspend (StaffOperationsApi) -> StaffContent) {
        val identity = requireSession()
        val request = screenStore.begin(identity)
        screenStore.publish(identity, request, StaffScreenState(loading = true))
        try {
            val content = block(api(identity))
            checkSession(identity)
            screenStore.publish(identity, request, StaffScreenState(content = content))
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: Exception) {
            checkSession(identity)
            screenStore.publish(identity, request, StaffScreenState(error = staffError(error)))
        }
    }

    suspend fun directory(query: String, favourites: Boolean, page: Int) = load { api ->
        val response = api.directory(query.take(100), favourites, page)
        StaffContent.Directory(response.results.filter { it.isActive }.map { it.toContact() }, response.next != null)
    }

    suspend fun contact(id: Long) = load { api ->
        val row = api.directoryContact(id)
        check(row.isActive) { "Contact is inactive" }
        StaffContent.Contact(row.toContact())
    }

    suspend fun favourite(id: Long, favourite: Boolean) = load { api ->
        api.setDirectoryFavourite(id, FavouriteRequestDto(favourite))
        val row = api.directoryContact(id)
        check(row.isActive) { "Contact is inactive" }
        StaffContent.Contact(row.toContact())
    }

    suspend fun announcementList(page: Int) = load { api ->
        val started = monotonicMillis()
        val response = api.staffAnnouncements(page)
        val clock = StaffServerClock.from(response.serverNow, started)
        StaffContent.Announcements(response.results.map { it.toAnnouncement() }.filter { clock?.isVisible(it, monotonicMillis()) == true }, response.next != null, clock)
    }

    suspend fun announcement(id: Long) = load { api ->
        val started = monotonicMillis()
        val row = api.staffAnnouncement(id)
        val clock = StaffServerClock.from(row.serverNow, started)
        val mapped = row.toAnnouncement()
        check(clock?.isVisible(mapped, monotonicMillis()) == true) { "Announcement expired" }
        StaffContent.Announcement(mapped, requireNotNull(clock))
    }

    suspend fun reminders(status: String, page: Int) = load { api ->
        val result = api.reminderOccurrences(status = status, page = page)
        StaffContent.Reminders(result.results, result.next != null, result.serverToday)
    }

    suspend fun reminder(id: Long, page: Int) = load { api -> reminderContent(api, id, page) }

    private suspend fun reminderContent(api: StaffOperationsApi, id: Long, page: Int): StaffContent.Reminder {
        val definition = api.staffReminder(id)
        val history = api.reminderOccurrences(status = "all", reminderId = id, page = page)
        return StaffContent.Reminder(definition, history.results, history.next != null)
    }

    suspend fun assignees(definition: StaffReminderDto, query: String, page: Int) = load { api ->
        // Retain the version that the assignment editor opened with.
        val result = api.reminderAssignees(query.take(100), page)
        StaffContent.Assignees(definition, result.results, result.next != null)
    }

    suspend fun assign(definition: StaffReminderDto, assigneeId: Long) = load { api ->
        api.assignReminder(definition.id, ReminderAssignmentRequestDto(definition.version, assigneeId))
        reminderContent(api, definition.id, 1)
    }

    suspend fun complete(occurrence: ReminderOccurrenceDto, page: Int) = load { api ->
        api.completeReminder(occurrence.id, ReminderCompleteRequestDto(occurrence.definitionVersion))
        reminderContent(api, occurrence.reminderId, page)
    }

    suspend fun refreshDueNotices() {
        val identity = requireSession()
        val request = noticeStore.begin(identity)
        try {
            val result = api(identity).reminderOccurrences(status = "notices")
            checkSession(identity)
            noticeStore.publish(identity, request, result.count)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: Exception) {
            // No stale notices after a failed fresh scope check.
        }
    }

    suspend fun refreshBanner() {
        val identity = requireSession()
        val request = bannerStore.begin(identity)
        try {
            val started = monotonicMillis()
            val response = api(identity).staffAnnouncements()
            checkSession(identity)
            val clock = StaffServerClock.from(response.serverNow, started)
            synchronized(this) {
                checkSession(identity)
                if (bannerStore.publish(identity, request, response.results.map { it.toAnnouncement() }
                        .filter { clock?.isVisible(it, monotonicMillis()) == true })) serverClock = clock
            }
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: Exception) {
            // A failed fresh read leaves the banner empty, never stale or from another audience.
        }
    }

    @Synchronized
    fun visibleAnnouncements(): List<StaffAnnouncement> = announcements.value.filter {
        serverClock?.isVisible(it, monotonicMillis()) == true
    }
}

private fun DirectoryContactDto.toContact() = DirectoryContact(
    id, name, roleSpecialty, organization, notes,
    phones.map { DirectoryPhone(it.label, it.number, it.extension) }, isFavourite,
)

private fun StaffAnnouncementDto.toAnnouncement() = StaffAnnouncement(
    id, text.lineSequence().first().take(100), text, priority, publisher?.name ?: "Former staff", startsAt, endsAt,
)

private fun staffError(error: Exception): String = when ((error as? HttpException)?.code()) {
    401, 403 -> "Access is no longer available."
    404 -> "This item is no longer available."
    409 -> "This item changed. Refresh before trying again."
    else -> "Unable to load staff tools. Check your connection and retry."
}
