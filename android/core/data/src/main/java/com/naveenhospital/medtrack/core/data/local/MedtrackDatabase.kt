package com.naveenhospital.medtrack.core.data.local

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.room.withTransaction
import androidx.sqlite.db.SupportSQLiteDatabase
import java.io.File
import net.zetetic.database.sqlcipher.SupportOpenHelperFactory

class AccountGenerationRevokedException : IllegalStateException(
    "The authenticated MEDTRACK account generation was revoked.",
)

@Database(
    entities = [
        AccountLifecycleEntity::class,
        CaseEntity::class,
        CaseStatsEntity::class,
        TaskEntity::class,
        VitalEntity::class,
        VitalsThresholdEntity::class,
        CategoryOptionsEntity::class,
        NotificationEntity::class,
        PushTokenEntity::class,
        PendingWriteEntity::class,
        SyncConflictEntity::class,
        CacheMetadataEntity::class,
    ],
    version = 13,
    exportSchema = true,
)
abstract class MedtrackDatabase : RoomDatabase() {
    abstract fun accountLifecycleDao(): AccountLifecycleDao
    abstract fun caseDao(): CaseDao
    abstract fun caseStatsDao(): CaseStatsDao
    abstract fun taskDao(): TaskDao
    abstract fun vitalDao(): VitalDao
    abstract fun vitalsThresholdDao(): VitalsThresholdDao
    abstract fun categoryOptionsDao(): CategoryOptionsDao
    abstract fun notificationDao(): NotificationDao
    abstract fun pushTokenDao(): PushTokenDao
    abstract fun pendingWriteDao(): PendingWriteDao
    abstract fun syncConflictDao(): SyncConflictDao
    abstract fun cacheMetadataDao(): CacheMetadataDao

    suspend fun activateAccount(ownerAccountId: String): Long = withTransaction {
        require(ownerAccountId.isNotBlank()) { "A verified account ID is required." }
        val previousGeneration = accountLifecycleDao().lifecycle(ownerAccountId)?.generation ?: 0L
        val generation = previousGeneration + 1L
        accountLifecycleDao().upsertLifecycle(
            AccountLifecycleEntity(
                ownerAccountId = ownerAccountId,
                generation = generation,
                isActive = true,
                updatedAtMillis = System.currentTimeMillis(),
            ),
        )
        generation
    }

    suspend fun activeAccountGeneration(ownerAccountId: String): Long? =
        accountLifecycleDao().lifecycle(ownerAccountId)
            ?.takeIf(AccountLifecycleEntity::isActive)
            ?.generation

    suspend fun <T> commitForAccount(
        ownerAccountId: String,
        generation: Long,
        isLocallyActive: () -> Boolean = { true },
        block: suspend () -> T,
    ): T = withTransaction {
        checkAccountGeneration(ownerAccountId, generation, isLocallyActive)
        val result = block()
        checkAccountGeneration(ownerAccountId, generation, isLocallyActive)
        result
    }

    suspend fun invalidateAndClearAccountData(
        ownerAccountId: String,
        expectedGeneration: Long? = null,
    ): Boolean = withTransaction {
        val lifecycle = accountLifecycleDao().lifecycle(ownerAccountId)
        if (
            expectedGeneration != null &&
            (lifecycle?.isActive != true || lifecycle.generation != expectedGeneration)
        ) {
            return@withTransaction false
        }
        val previousGeneration = lifecycle?.generation ?: 0L
        accountLifecycleDao().upsertLifecycle(
            AccountLifecycleEntity(
                ownerAccountId = ownerAccountId,
                generation = previousGeneration + 1L,
                isActive = false,
                updatedAtMillis = System.currentTimeMillis(),
            ),
        )
        pendingWriteDao().clearForOwner(ownerAccountId)
        syncConflictDao().clearForOwner(ownerAccountId)
        notificationDao().clearForOwner(ownerAccountId)
        pushTokenDao().clearForOwner(ownerAccountId)
        taskDao().clearForOwner(ownerAccountId)
        vitalDao().clearForOwner(ownerAccountId)
        caseDao().clearCases(ownerAccountId)
        caseStatsDao().clearForOwner(ownerAccountId)
        vitalsThresholdDao().clearForOwner(ownerAccountId)
        categoryOptionsDao().clearForOwner(ownerAccountId)
        cacheMetadataDao().clearForOwner(ownerAccountId)
        true
    }

    private suspend fun checkAccountGeneration(
        ownerAccountId: String,
        generation: Long,
        isLocallyActive: () -> Boolean,
    ) {
        if (!isLocallyActive()) throw AccountGenerationRevokedException()
        val lifecycle = accountLifecycleDao().lifecycle(ownerAccountId)
        if (lifecycle?.isActive != true || lifecycle.generation != generation) {
            throw AccountGenerationRevokedException()
        }
    }

    companion object {
        @Volatile
        private var INSTANCE: MedtrackDatabase? = null

        fun build(context: Context): MedtrackDatabase =
            INSTANCE ?: synchronized(this) {
                val appContext = context.applicationContext
                INSTANCE ?: Room.databaseBuilder(
                    appContext,
                    MedtrackDatabase::class.java,
                    ENCRYPTED_DATABASE_NAME,
                )
                    .openHelperFactory(sqlCipherFactory(appContext))
                    .addMigrations(
                        MIGRATION_1_2,
                        MIGRATION_2_3,
                        MIGRATION_3_4,
                        MIGRATION_4_5,
                        MIGRATION_5_6,
                        MIGRATION_6_7,
                        MIGRATION_7_8,
                        MIGRATION_8_9,
                        MIGRATION_9_10,
                        MIGRATION_10_11,
                        MIGRATION_11_12,
                        MIGRATION_12_13,
                    )
                    .build()
                    .also { INSTANCE = it }
            }

        private const val ENCRYPTED_DATABASE_NAME = "medtrack_secure.db"
        private const val LEGACY_PLAINTEXT_DATABASE_NAME = "medtrack.db"

        private fun sqlCipherFactory(context: Context): SupportOpenHelperFactory {
            deleteLegacyPlaintextDatabase(context)
            System.loadLibrary("sqlcipher")
            return SupportOpenHelperFactory(DatabaseKeyStore(context).getOrCreatePassphrase())
        }

        private fun deleteLegacyPlaintextDatabase(context: Context) {
            val database = context.getDatabasePath(LEGACY_PLAINTEXT_DATABASE_NAME)
            val legacyFiles = listOf(
                database,
                File(database.path + "-wal"),
                File(database.path + "-shm"),
                File(database.path + "-journal"),
            )
            if (database.exists()) {
                context.deleteDatabase(LEGACY_PLAINTEXT_DATABASE_NAME)
            }
            legacyFiles.filter(File::exists).forEach { file ->
                check(file.delete() || !file.exists()) {
                    "Refusing to continue while legacy plaintext MEDTRACK storage remains."
                }
            }
        }

        private val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE cases ADD COLUMN subcategoryValue TEXT")
            }
        }

        private val MIGRATION_2_3 = object : Migration(2, 3) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS tasks (
                        id TEXT NOT NULL PRIMARY KEY,
                        caseId TEXT NOT NULL,
                        title TEXT NOT NULL,
                        dueDate TEXT,
                        status TEXT NOT NULL,
                        statusLabel TEXT NOT NULL,
                        canComplete INTEGER NOT NULL,
                        updatedAtMillis INTEGER NOT NULL
                    )
                    """.trimIndent(),
                )
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS vitals (
                        id TEXT NOT NULL PRIMARY KEY,
                        caseId TEXT NOT NULL,
                        recordedAt TEXT NOT NULL,
                        bpSystolic INTEGER,
                        bpDiastolic INTEGER,
                        pulse INTEGER,
                        spo2 INTEGER,
                        weightKg TEXT,
                        hemoglobin TEXT,
                        summary TEXT NOT NULL,
                        updatedAtMillis INTEGER NOT NULL
                    )
                    """.trimIndent(),
                )
            }
        }

        private val MIGRATION_3_4 = object : Migration(3, 4) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS vitals_thresholds (
                        id TEXT NOT NULL PRIMARY KEY,
                        payloadJson TEXT NOT NULL,
                        updatedAtMillis INTEGER NOT NULL
                    )
                    """.trimIndent(),
                )
            }
        }

        private val MIGRATION_4_5 = object : Migration(4, 5) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS sync_conflicts (
                        clientWriteId TEXT NOT NULL PRIMARY KEY,
                        writeType TEXT NOT NULL,
                        caseId TEXT,
                        taskId TEXT,
                        message TEXT NOT NULL,
                        serverPayloadJson TEXT,
                        createdAtMillis INTEGER NOT NULL
                    )
                    """.trimIndent(),
                )
            }
        }

        private val MIGRATION_5_6 = object : Migration(5, 6) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS cache_metadata (
                        cacheKey TEXT NOT NULL PRIMARY KEY,
                        updatedAtMillis INTEGER NOT NULL
                    )
                    """.trimIndent(),
                )
            }
        }

        private val MIGRATION_6_7 = object : Migration(6, 7) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS case_stats (
                        cacheKey TEXT NOT NULL PRIMARY KEY,
                        today INTEGER NOT NULL,
                        upcoming INTEGER NOT NULL,
                        overdue INTEGER NOT NULL,
                        awaiting INTEGER NOT NULL,
                        red INTEGER NOT NULL,
                        updatedAtMillis INTEGER NOT NULL
                    )
                    """.trimIndent(),
                )
            }
        }

        private val MIGRATION_7_8 = object : Migration(7, 8) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS category_options (
                        id TEXT NOT NULL PRIMARY KEY,
                        payloadJson TEXT NOT NULL,
                        updatedAtMillis INTEGER NOT NULL
                    )
                    """.trimIndent(),
                )
            }
        }

        private val MIGRATION_8_9 = object : Migration(8, 9) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE notifications ADD COLUMN payloadJson TEXT NOT NULL DEFAULT '{}'")
            }
        }

        private val MIGRATION_9_10 = object : Migration(9, 10) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE tasks ADD COLUMN taskType TEXT")
                db.execSQL("ALTER TABLE tasks ADD COLUMN taskTypeLabel TEXT")
                db.execSQL("ALTER TABLE tasks ADD COLUMN assignedUserId INTEGER")
                db.execSQL("ALTER TABLE tasks ADD COLUMN assignedUser TEXT")
                db.execSQL("ALTER TABLE tasks ADD COLUMN notes TEXT")
            }
        }

        /**
         * V1-V10 rows had no trustworthy account owner. Assigning them to the next login
         * could expose PHI or replay another user's outbox, so the ownership transition is
         * deliberately destructive for local-only cache/outbox data. Server data is resynced
         * only after a verified /me identity is committed.
         */
        internal val MIGRATION_10_11 = object : Migration(10, 11) {
            override fun migrate(db: SupportSQLiteDatabase) {
                listOf(
                    "cases",
                    "case_stats",
                    "tasks",
                    "vitals",
                    "vitals_thresholds",
                    "category_options",
                    "notifications",
                    "push_tokens",
                    "pending_writes",
                    "sync_conflicts",
                    "cache_metadata",
                ).forEach { table -> db.execSQL("DROP TABLE IF EXISTS `$table`") }

                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS `cases` (
                        `ownerAccountId` TEXT NOT NULL,
                        `id` TEXT NOT NULL,
                        `uhid` TEXT NOT NULL,
                        `patientName` TEXT NOT NULL,
                        `age` INTEGER,
                        `sexLabel` TEXT,
                        `place` TEXT,
                        `phoneNumber` TEXT,
                        `category` TEXT NOT NULL,
                        `subcategoryValue` TEXT,
                        `subcategoryLabel` TEXT,
                        `status` TEXT NOT NULL,
                        `diagnosis` TEXT NOT NULL,
                        `nextTaskId` TEXT,
                        `nextTaskTitle` TEXT,
                        `nextTaskDueDate` TEXT,
                        `latestVitalSummary` TEXT,
                        `isHighRisk` INTEGER NOT NULL,
                        `highRiskReasons` TEXT NOT NULL,
                        `updatedAtMillis` INTEGER NOT NULL,
                        PRIMARY KEY(`ownerAccountId`, `id`)
                    )
                    """.trimIndent(),
                )
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS `case_stats` (
                        `ownerAccountId` TEXT NOT NULL,
                        `cacheKey` TEXT NOT NULL,
                        `today` INTEGER NOT NULL,
                        `upcoming` INTEGER NOT NULL,
                        `overdue` INTEGER NOT NULL,
                        `awaiting` INTEGER NOT NULL,
                        `red` INTEGER NOT NULL,
                        `updatedAtMillis` INTEGER NOT NULL,
                        PRIMARY KEY(`ownerAccountId`, `cacheKey`)
                    )
                    """.trimIndent(),
                )
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS `tasks` (
                        `ownerAccountId` TEXT NOT NULL,
                        `id` TEXT NOT NULL,
                        `caseId` TEXT NOT NULL,
                        `title` TEXT NOT NULL,
                        `dueDate` TEXT,
                        `status` TEXT NOT NULL,
                        `statusLabel` TEXT NOT NULL,
                        `canComplete` INTEGER NOT NULL,
                        `taskType` TEXT,
                        `taskTypeLabel` TEXT,
                        `assignedUserId` INTEGER,
                        `assignedUser` TEXT,
                        `notes` TEXT,
                        `updatedAtMillis` INTEGER NOT NULL,
                        PRIMARY KEY(`ownerAccountId`, `id`)
                    )
                    """.trimIndent(),
                )
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS `vitals` (
                        `ownerAccountId` TEXT NOT NULL,
                        `id` TEXT NOT NULL,
                        `caseId` TEXT NOT NULL,
                        `recordedAt` TEXT NOT NULL,
                        `bpSystolic` INTEGER,
                        `bpDiastolic` INTEGER,
                        `pulse` INTEGER,
                        `spo2` INTEGER,
                        `weightKg` TEXT,
                        `hemoglobin` TEXT,
                        `summary` TEXT NOT NULL,
                        `updatedAtMillis` INTEGER NOT NULL,
                        PRIMARY KEY(`ownerAccountId`, `id`)
                    )
                    """.trimIndent(),
                )
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS `vitals_thresholds` (
                        `ownerAccountId` TEXT NOT NULL,
                        `id` TEXT NOT NULL,
                        `payloadJson` TEXT NOT NULL,
                        `updatedAtMillis` INTEGER NOT NULL,
                        PRIMARY KEY(`ownerAccountId`, `id`)
                    )
                    """.trimIndent(),
                )
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS `category_options` (
                        `ownerAccountId` TEXT NOT NULL,
                        `id` TEXT NOT NULL,
                        `payloadJson` TEXT NOT NULL,
                        `updatedAtMillis` INTEGER NOT NULL,
                        PRIMARY KEY(`ownerAccountId`, `id`)
                    )
                    """.trimIndent(),
                )
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS `notifications` (
                        `ownerAccountId` TEXT NOT NULL,
                        `id` TEXT NOT NULL,
                        `type` TEXT NOT NULL,
                        `title` TEXT NOT NULL,
                        `body` TEXT NOT NULL,
                        `caseId` TEXT,
                        `taskId` TEXT,
                        `createdAt` TEXT NOT NULL,
                        `isRead` INTEGER NOT NULL,
                        `payloadJson` TEXT NOT NULL DEFAULT '{}',
                        PRIMARY KEY(`ownerAccountId`, `id`)
                    )
                    """.trimIndent(),
                )
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS `push_tokens` (
                        `ownerAccountId` TEXT NOT NULL,
                        `token` TEXT NOT NULL,
                        `deviceLabel` TEXT NOT NULL,
                        `syncedAtMillis` INTEGER NOT NULL,
                        PRIMARY KEY(`ownerAccountId`, `token`)
                    )
                    """.trimIndent(),
                )
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS `pending_writes` (
                        `ownerAccountId` TEXT NOT NULL,
                        `clientWriteId` TEXT NOT NULL,
                        `writeType` TEXT NOT NULL,
                        `caseId` TEXT,
                        `taskId` TEXT,
                        `payloadJson` TEXT NOT NULL,
                        `retryCount` INTEGER NOT NULL,
                        `lastError` TEXT,
                        `createdAtMillis` INTEGER NOT NULL,
                        `updatedAtMillis` INTEGER NOT NULL,
                        PRIMARY KEY(`ownerAccountId`, `clientWriteId`)
                    )
                    """.trimIndent(),
                )
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS `sync_conflicts` (
                        `ownerAccountId` TEXT NOT NULL,
                        `clientWriteId` TEXT NOT NULL,
                        `writeType` TEXT NOT NULL,
                        `caseId` TEXT,
                        `taskId` TEXT,
                        `message` TEXT NOT NULL,
                        `serverPayloadJson` TEXT,
                        `createdAtMillis` INTEGER NOT NULL,
                        PRIMARY KEY(`ownerAccountId`, `clientWriteId`)
                    )
                    """.trimIndent(),
                )
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS `cache_metadata` (
                        `ownerAccountId` TEXT NOT NULL,
                        `cacheKey` TEXT NOT NULL,
                        `updatedAtMillis` INTEGER NOT NULL,
                        PRIMARY KEY(`ownerAccountId`, `cacheKey`)
                    )
                    """.trimIndent(),
                )
            }
        }

        internal val MIGRATION_11_12 = object : Migration(11, 12) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL(
                    """
                    CREATE TABLE IF NOT EXISTS `account_lifecycle` (
                        `ownerAccountId` TEXT NOT NULL,
                        `generation` INTEGER NOT NULL,
                        `isActive` INTEGER NOT NULL,
                        `updatedAtMillis` INTEGER NOT NULL,
                        PRIMARY KEY(`ownerAccountId`)
                    )
                    """.trimIndent(),
                )
            }
        }

        internal val MIGRATION_12_13 = object : Migration(12, 13) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE cases ADD COLUMN followUpLabel TEXT NOT NULL DEFAULT ''")
                db.execSQL("ALTER TABLE cases ADD COLUMN ancOutcomeSummary TEXT NOT NULL DEFAULT ''")
                db.execSQL("ALTER TABLE cases ADD COLUMN serverUpdatedAt TEXT NOT NULL DEFAULT ''")
                db.execSQL("ALTER TABLE case_stats ADD COLUMN dormant INTEGER NOT NULL DEFAULT 0")
            }
        }

        internal val ALL_MIGRATIONS: Array<Migration> = arrayOf(
            MIGRATION_1_2,
            MIGRATION_2_3,
            MIGRATION_3_4,
            MIGRATION_4_5,
            MIGRATION_5_6,
            MIGRATION_6_7,
            MIGRATION_7_8,
            MIGRATION_8_9,
            MIGRATION_9_10,
            MIGRATION_10_11,
            MIGRATION_11_12,
            MIGRATION_12_13,
        )
    }
}
