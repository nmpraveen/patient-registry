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

    @Test
    fun everySupportedSchemaVersionMigratesToCurrentSchema() {
        (1..12).forEach { startVersion ->
            val databaseName = "migration_${startVersion}_to_13"
            helper.createDatabase(databaseName, startVersion).close()

            helper.runMigrationsAndValidate(
                databaseName,
                13,
                true,
                *MedtrackDatabase.ALL_MIGRATIONS,
            ).use { database ->
                database.query("PRAGMA user_version").use { cursor ->
                    assertTrue(cursor.moveToFirst())
                    assertEquals(13, cursor.getInt(0))
                }
            }
        }
    }

    @Test
    fun ownershipTransitionDropsUnownedOutboxAndAcceptsSameKeyForTwoAccounts() {
        val databaseName = "migration_ownership_transition"
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
            13,
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
        val databaseName = "migration_11_to_13_owned_rows"
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
            13,
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
