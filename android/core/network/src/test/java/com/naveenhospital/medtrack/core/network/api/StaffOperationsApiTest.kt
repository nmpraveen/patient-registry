package com.naveenhospital.medtrack.core.network.api

import com.naveenhospital.medtrack.core.network.model.FavouriteRequestDto
import com.naveenhospital.medtrack.core.network.model.ReminderCompleteRequestDto
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.*
import org.junit.Test

class StaffOperationsApiTest {
    private val contact = """{"id":1,"name":"Switchboard","role_specialty":"Desk","organization":"Demo","phones":[{"label":"Desk","number":"123456","extension":"22"}],"notes":"","is_active":true,"is_favourite":true,"version":3}"""

    @Test fun directorySearchUsesAgreedScopedRouteAndFavouriteIsPutSet() = runBlocking {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setBody("""{"count":1,"next":null,"previous":null,"results":[$contact]}"""))
            server.enqueue(MockResponse().setBody(contact))
            val api = MedtrackNetwork.create(server.url("/").toString(), accessTokenProvider = { "synthetic" })
            assertEquals("22", api.directory("Switchboard", true, 2).results.single().phones.single().extension)
            val search = server.takeRequest()
            assertEquals("/api/staff/directory/?q=Switchboard&favourites=true&page=2", search.path)
            assertEquals("Bearer synthetic", search.getHeader("Authorization"))
            assertTrue(api.setDirectoryFavourite(1, FavouriteRequestDto(true)).isFavourite)
            val write = server.takeRequest()
            assertEquals("PUT", write.method)
            assertEquals("/api/staff/directory/1/favourite/", write.path)
            assertEquals("{\"is_favourite\":true}", write.body.readUtf8())
        }
    }

    @Test fun completionSendsDefinitionVersionToOccurrenceAndPreservesReceipt() = runBlocking {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setBody("""{"id":7,"reminder_id":3,"title":"Check supplies","assignee_id":1,"assignee_name":"Staff One","due_date":"2026-09-08","notice_date":"2026-09-07","completed_at":"2026-09-08T00:00:00Z","completed_by_id":1,"is_active":true,"can_complete":false,"definition_version":4}"""))
            val api = MedtrackNetwork.create(server.url("/").toString())
            val receipt = api.completeReminder(7, ReminderCompleteRequestDto(4))
            assertEquals("2026-09-08T00:00:00Z", receipt.completedAt)
            assertFalse(receipt.canComplete)
            val write = server.takeRequest()
            assertEquals("POST", write.method)
            assertEquals("/api/staff/reminders/occurrences/7/complete/", write.path)
            assertEquals("{\"version\":4}", write.body.readUtf8())
        }
    }

    @Test fun announcementListParsesServerTimeAndNeverRequestsManagementAudience() = runBlocking {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setBody("""{"count":1,"next":null,"previous":null,"server_now":"2026-09-07T00:00:00Z","results":[{"id":1,"text":"Supplies delivery","priority":"normal","audience":"all_staff","starts_at":"2026-09-07T00:00:00Z","ends_at":"2026-09-07T01:00:00Z","publisher":{"id":1,"name":"Staff One"},"version":1}]}"""))
            val api = MedtrackNetwork.create(server.url("/").toString())
            val result = api.staffAnnouncements()
            assertEquals("2026-09-07T00:00:00Z", result.serverNow)
            assertEquals("Staff One", result.results.single().publisher.name)
            assertEquals("/api/staff/announcements/?page=1", server.takeRequest().path)
        }
    }
}
