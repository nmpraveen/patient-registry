package com.naveenhospital.medtrack.core.data.repository

import com.naveenhospital.medtrack.core.data.auth.AccountSessionIdentity
import com.naveenhospital.medtrack.core.domain.model.StaffAnnouncement
import com.naveenhospital.medtrack.core.network.api.StaffOperationsApi
import com.naveenhospital.medtrack.core.network.model.*
import java.io.IOException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.runTest
import org.junit.Assert.*
import org.junit.Test

class StaffToolsRepositoryTest {
    private val identity = AccountSessionIdentity("1", "one")
    private fun repository(api: StaffOperationsApi) = StaffToolsRepository({ api }, { it == identity }, { 0L }).apply { activate(identity) }
    private val contact = DirectoryContactDto(1, "Switchboard", phones = listOf(DirectoryPhoneDto("Desk", "123456")), isActive = true, isFavourite = false, version = 2)
    private val occurrence = ReminderOccurrenceDto(7, 3, "Check supplies", 1, "Staff One", "2026-09-08", "2026-09-07", isActive = true, canComplete = true, definitionVersion = 4)
    private val definition = StaffReminderDto(3, "Check supplies", 1, 1, "Staff One", true, "2026-09-08", 1, "ONCE", true, 4, true, true)

    @Test fun delayedNetworkResponseCannotRepopulateAfterRevocation() = runTest {
        val entered = CompletableDeferred<Unit>()
        val release = CompletableDeferred<Unit>()
        val api = object : StaffApiStub() {
            override suspend fun directory(query: String, favourites: Boolean, page: Int): StaffPageDto<DirectoryContactDto> {
                entered.complete(Unit); release.await()
                return StaffPageDto(1, results = listOf(contact))
            }
        }
        val repository = repository(api)
        val job = launch { repository.directory("", false, 1) }
        entered.await()
        repository.activate(null)
        release.complete(Unit)
        job.join()
        assertNull(repository.screen.value.content)
        assertNull(repository.activeSession.value)
    }

    @Test fun failedRefreshClearsPriorDirectoryAndDeactivationCannotShowDetail() = runTest {
        var fail = false
        val api = object : StaffApiStub() {
            override suspend fun directory(query: String, favourites: Boolean, page: Int): StaffPageDto<DirectoryContactDto> {
                if (fail) throw IOException("offline")
                return StaffPageDto(1, results = listOf(contact))
            }
            override suspend fun directoryContact(id: Long) = contact.copy(isActive = false)
        }
        val repository = repository(api)
        repository.directory("", false, 1)
        assertNotNull(repository.screen.value.content)
        fail = true
        repository.directory("", false, 1)
        assertNull(repository.screen.value.content)
        assertNotNull(repository.screen.value.error)
        repository.contact(1)
        assertNull(repository.screen.value.content)
    }

    @Test fun completionUsesOccurrenceIdentityAndOriginalVersionThenReadsHistory() = runTest {
        var sentId: Long? = null
        var sentVersion: Long? = null
        val api = object : StaffApiStub() {
            override suspend fun completeReminder(id: Long, request: ReminderCompleteRequestDto): ReminderOccurrenceDto {
                sentId = id; sentVersion = request.version
                return occurrence.copy(completedAt = "2026-09-08T00:00:00Z", completedById = 1, canComplete = false)
            }
            override suspend fun staffReminder(id: Long) = definition
            override suspend fun reminderOccurrences(status: String, reminderId: Long?, page: Int): StaffPageDto<ReminderOccurrenceDto> {
                assertEquals("all", status); assertEquals(3L, reminderId)
                return StaffPageDto(1, results = listOf(occurrence.copy(completedAt = "2026-09-08T00:00:00Z")))
            }
        }
        val repository = repository(api)
        repository.complete(occurrence, 1)
        assertEquals(7L, sentId)
        assertEquals(4L, sentVersion)
        assertNotNull((repository.screen.value.content as StaffContent.Reminder).history.single().completedAt)
    }

    @Test fun favouriteIsExplicitSetAndReceiptFollowedByFreshActiveContact() = runTest {
        var favourite = false
        val api = object : StaffApiStub() {
            override suspend fun setDirectoryFavourite(id: Long, request: FavouriteRequestDto): DirectoryContactDto {
                favourite = request.isFavourite
                return contact.copy(isFavourite = favourite)
            }
            override suspend fun directoryContact(id: Long) = contact.copy(isFavourite = favourite)
        }
        val repository = repository(api)
        repeat(2) { repository.favourite(1, true) }
        assertTrue((repository.screen.value.content as StaffContent.Contact).row.favourite)
    }

    @Test fun expiryUsesServerClockWithInclusiveStartExclusiveEnd() {
        val row = StaffAnnouncement(1, "Notice", "Notice", "normal", "Staff", "2026-09-07T00:00:00Z", "2026-09-07T00:01:00Z")
        val clock = requireNotNull(StaffServerClock.from(row.startsAt, 10_000))
        assertTrue(clock.isVisible(row, 10_000))
        assertTrue(clock.isVisible(row, 69_999))
        assertFalse(clock.isVisible(row, 70_000))
        assertFalse(clock.isVisible(row.copy(startsAt = "invalid"), 10_000))
        assertEquals(parseStaffTimestamp("2026-09-07T00:00:00.123456Z"), parseStaffTimestamp("2026-09-07T05:30:00.123+05:30"))
        assertNull(parseStaffTimestamp("2026-02-30T00:00:00Z"))
    }

    @Test fun slowAnnouncementResponseCannotExtendExpiry() = runTest {
        var elapsed = 0L
        val api = object : StaffApiStub() {
            override suspend fun staffAnnouncements(page: Int): StaffPageDto<StaffAnnouncementDto> {
                elapsed = 70_000
                return StaffPageDto(1, results = listOf(StaffAnnouncementDto(
                    1, "Notice", "normal", "all_staff", "2026-09-07T00:00:00Z", "2026-09-07T00:01:00Z", StaffPersonDto(1, "Staff"), 1,
                )), serverNow = "2026-09-07T00:00:00Z")
            }
        }
        val repository = StaffToolsRepository({ api }, { it == identity }, { elapsed }).apply { activate(identity) }
        repository.refreshBanner()
        assertTrue(repository.visibleAnnouncements().isEmpty())
    }

    @Test fun assignmentSendsDisplayedVersionAndNeverRetriesWithNewBaseline() = runTest {
        var writes = 0
        val api = object : StaffApiStub() {
            override suspend fun assignReminder(id: Long, request: ReminderAssignmentRequestDto): StaffReminderDto {
                writes++
                assertEquals(4L, request.version)
                assertEquals(2L, request.assigneeId)
                throw IOException("Response lost")
            }
        }
        val repository = repository(api)
        repository.assign(definition, 2)
        assertEquals(1, writes)
        assertNull(repository.screen.value.content)
        assertNotNull(repository.screen.value.error)
    }
}

private abstract class StaffApiStub : StaffOperationsApi {
    override suspend fun directory(query: String, favourites: Boolean, page: Int): StaffPageDto<DirectoryContactDto> = error("Unexpected directory")
    override suspend fun directoryContact(id: Long): DirectoryContactDto = error("Unexpected contact")
    override suspend fun setDirectoryFavourite(id: Long, request: FavouriteRequestDto): DirectoryContactDto = error("Unexpected favourite")
    override suspend fun staffAnnouncements(page: Int): StaffPageDto<StaffAnnouncementDto> = error("Unexpected announcements")
    override suspend fun staffAnnouncement(id: Long): StaffAnnouncementDto = error("Unexpected announcement")
    override suspend fun reminderOccurrences(status: String, reminderId: Long?, page: Int): StaffPageDto<ReminderOccurrenceDto> = error("Unexpected occurrences")
    override suspend fun staffReminder(id: Long): StaffReminderDto = error("Unexpected reminder")
    override suspend fun reminderAssignees(query: String, page: Int): StaffPageDto<StaffPersonDto> = error("Unexpected assignees")
    override suspend fun assignReminder(id: Long, request: ReminderAssignmentRequestDto): StaffReminderDto = error("Unexpected assignment")
    override suspend fun completeReminder(id: Long, request: ReminderCompleteRequestDto): ReminderOccurrenceDto = error("Unexpected completion")
}
