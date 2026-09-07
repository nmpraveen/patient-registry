package com.naveenhospital.medtrack.core.data.local

import androidx.room.testing.MigrationTestHelper
import androidx.sqlite.db.framework.FrameworkSQLiteOpenHelperFactory
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class MedtrackDatabaseMigrationTest {
    @get:Rule
    val helper = MigrationTestHelper(
        InstrumentationRegistry.getInstrumentation(),
        MedtrackDatabase::class.java,
        emptyList(),
        FrameworkSQLiteOpenHelperFactory(),
    )

    // Room 2.8 compares the configured name with the opened path. An absolute
    // name works on both Android/Linux and Windows Robolectric sandboxes.
    private fun databasePath(name: String): String =
        InstrumentationRegistry.getInstrumentation().targetContext.getDatabasePath(name).absolutePath

    @Test
    fun everySupportedSchemaVersionMigratesToCurrentSchema() {
        (1..11).forEach { startVersion ->
            val databaseName = databasePath("migration_${startVersion}_to_12")
            helper.createDatabase(databaseName, startVersion).close()

            helper.runMigrationsAndValidate(
                databaseName,
                12,
                true,
                *MedtrackDatabase.ALL_MIGRATIONS,
            ).use { database ->
                database.query("PRAGMA user_version").use { cursor ->
                    assertTrue(cursor.moveToFirst())
                    assertEquals(12, cursor.getInt(0))
                }
            }
        }
    }

    @Test
    fun ownershipTransitionDropsUnownedOutboxAndAcceptsSameKeyForTwoAccounts() {
        val databaseName = databasePath("migration_ownership_transition")
        helper.createDatabase(databaseName, 10).use { database ->
            database.execSQL(
                """
                INSERT INTO pending_writes (
                    clientWriteId, writeType, caseId, taskId, payloadJson,
                    retryCount, lastError, createdAtMillis, updatedAtMillis
                ) VALUES ('shared-write', 'task_complete', '42', '7', '{}', 0, NULL, 1, 1)
                """.trimIndent(),
            )
        }

        helper.runMigrationsAndValidate(
            databaseName,
            12,
            true,
            *MedtrackDatabase.ALL_MIGRATIONS,
        ).use { database ->
            database.query("SELECT COUNT(*) FROM pending_writes").use { cursor ->
                assertTrue(cursor.moveToFirst())
                assertEquals(0, cursor.getInt(0))
            }

            listOf("account-a", "account-b").forEach { ownerAccountId ->
                database.execSQL(
                    """
                    INSERT INTO pending_writes (
                        ownerAccountId, clientWriteId, writeType, caseId, taskId,
                        payloadJson, retryCount, lastError, createdAtMillis, updatedAtMillis
                    ) VALUES (?, 'shared-write', 'task_complete', '42', '7', '{}', 0, NULL, 2, 2)
                    """.trimIndent(),
                    arrayOf(ownerAccountId),
                )
            }

            database.query(
                "SELECT ownerAccountId FROM pending_writes ORDER BY ownerAccountId",
            ).use { cursor ->
                assertEquals(2, cursor.count)
                assertTrue(cursor.moveToFirst())
                assertEquals("account-a", cursor.getString(0))
                assertTrue(cursor.moveToNext())
                assertEquals("account-b", cursor.getString(0))
            }
        }
    }

    @Test
    fun lifecycleUpgradePreservesV11OwnedRowsButRequiresFreshActivation() {
        val databaseName = databasePath("migration_11_to_12_owned_rows")
        helper.createDatabase(databaseName, 11).use { database ->
            database.execSQL(
                """
                INSERT INTO pending_writes (
                    ownerAccountId, clientWriteId, writeType, caseId, taskId,
                    payloadJson, retryCount, lastError, createdAtMillis, updatedAtMillis
                ) VALUES ('account-a', 'owned-write', 'task_complete', '42', '7', '{}', 0, NULL, 2, 2)
                """.trimIndent(),
            )
        }

        helper.runMigrationsAndValidate(
            databaseName,
            12,
            true,
            *MedtrackDatabase.ALL_MIGRATIONS,
        ).use { database ->
            database.query("SELECT ownerAccountId, clientWriteId FROM pending_writes").use { cursor ->
                assertTrue(cursor.moveToFirst())
                assertEquals("account-a", cursor.getString(0))
                assertEquals("owned-write", cursor.getString(1))
            }
            database.query("SELECT COUNT(*) FROM account_lifecycle").use { cursor ->
                assertTrue(cursor.moveToFirst())
                assertEquals(0, cursor.getInt(0))
            }
        }
    }
}
