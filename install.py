#!/usr/bin/python

import sys
import time
import warnings

try:
    import api
except ImportError:
    pass


class PostsaiInstaller:
    """Installer for Postsai"""

    @staticmethod
    def print_config_help_and_exit():
        help_config_file = """
    Please create a file called config.py with this content an run install.py again: 

import os

db = {
    "host" : "localhost",
    "user" : "postsaiuser",
    "password" : "postsaipassword",
    "database" : "postsaidb"
}

ui = {
    "avatar" : "https://gravatar.com",
    "trim_email" : True
}

def get_read_permission_pattern():
    \"""return a regular expression of repository names that may be read\"""

    # return os.environ.get("AUTHENTICATE_POSTSAI_READ_PATTERN", "^$")
    return ".*"

def get_write_permission_pattern():
    \"""return a regular expression of repository names that may be written to\"""

    # return os.environ.get("AUTHENTICATE_POSTSAI_WRITE_PATTERN", "^$")
    return ".*"
    """
        print(help_config_file)
        sys.exit(1)


    def import_config(self):
        try:
            import config
        except ImportError:
            self.print_config_help_and_exit()

        print("OK: Found config file")
        self.config = vars(config)


    def check_db_config(self):
        if not "db" in self.config:
            print("ERR: Missing parameter \"db\" in config file.")
            self.print_config_help_and_exit()

        for param in ["host", "user", "password", "database"]:
            if not param in self.config["db"]:
                print("ERR: Missing parameter in \"db\" section of config file.")
                self.print_config_help_and_exit()
        print "OK: Found database configuration"


    def connect(self):
        try:
            self.db = api.PostsaiDB(self.config)
            self.db.connect()
            print("OK: Connected to database")
        except Exception as err:
            print("ERR: Failed to connect to database \"" + self.config["db"]["database"] + "\":")
            print(err)
            sys.exit(1)


    def has_index(self, table, name):
        """checks whether the specified index exists on the specified table"""

        sql = "SHOW INDEX FROM " + table + " WHERE key_name = %s"
        data = [name]
        rows = self.db.query(self.db.rewrite_sql(sql), data)
        return len(rows) > 0


    def convert_to_innodb(self):
        """Converts all database tables to InnoDB"""

        sql = "ALTER TABLE `dirs` MODIFY COLUMN `dir` VARCHAR(254)"
        rows = self.db.query(sql, []);

        sql = "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = %s AND ENGINE = 'MyISAM'"
        data = [self.config["db"]["database"]]
        rows = self.db.query(sql, data);
        data = []
        for row in rows:
            self.db.query("ALTER TABLE " + row[0] + " ENGINE=INNODB", data);


    def convert_to_utf8(self):
        """Converts all database tables to UTF-8"""

        query = """SELECT table_name
FROM information_schema.tables, information_schema.collation_character_set_applicability
WHERE collation_character_set_applicability.collation_name = tables.table_collation
AND table_schema = %s AND character_set_name != 'utf8'"""
        data = [self.config["db"]["database"]]
        tables = self.db.query(query, data);

        for table in tables:
            self.db.query("ALTER TABLE " + table[0] + "  CONVERT TO CHARSET 'UTF8' COLLATE utf8_bin", []);
            cursor = self.db.conn.cursor()
            cursor.execute("SELECT * FROM " + table[0] + " WHERE 1=0")
            for column in cursor.description:
                if column[1] >= 252:
                    try:
                        cursor.execute("update " + table[0] + " set " + column[0] + " = @txt where char_length(" + column[0] + ") = length(@txt := convert(binary convert(" + column[0] + " using latin1) using utf8));")
                    except:
                        #print("E")
                        pass
            cursor.close()


    def update_database_structure(self):
        """alters the database structure"""

        cursor = self.db.conn.cursor()

        # fixed invalid default for ci_when, which prevents the next ALTER statement
        cursor.execute(self.db.rewrite_sql("ALTER TABLE commits CHANGE ci_when ci_when datetime NOT NULL DEFAULT current_timestamp;"))

        # increase column width of checkins
        cursor.execute(self.db.rewrite_sql("ALTER TABLE checkins CHANGE revision revision VARCHAR(50) NOT NULL;"))

        # add columns to repositories table
        cursor.execute("SELECT * FROM repositories WHERE 1=0")
        if len(cursor.description) < 3:
            cursor.execute("ALTER TABLE repositories ADD (base_url VARCHAR(255), repository_url varchar(255), file_url VARCHAR(255), commit_url VARCHAR(255), icon_url VARCHAR(255), tracker_url VARCHAR(255))")
        elif len(cursor.description) < 8:
            cursor.execute("ALTER TABLE repositories ADD (repository_url varchar(255))")


        # add columns to commitids table
        cursor.execute("SELECT * FROM commitids WHERE 1=0")
        if len(cursor.description) < 6:
            cursor.execute("ALTER TABLE commitids ADD (remote_addr VARCHAR(255), remote_user VARCHAR(255))")

        # add columns to checkins table
        cursor.execute(self.db.rewrite_sql("SELECT * FROM checkins WHERE 1=0"))
        if len(cursor.description) < 13:
            cursor.execute(self.db.rewrite_sql("ALTER TABLE checkins ADD (`id` mediumint(9) NOT NULL AUTO_INCREMENT, commitid mediumint(9), key commitid(commitid), PRIMARY KEY(id))"))

        cursor.close()


    def update_index_definitions(self):
        """Updates the definition of indexes"""

        if self.has_index("checkins", "repository"):
            self.db.query(self.db.rewrite_sql("ALTER TABLE checkins DROP INDEX repositoryid"), [])

        if not self.has_index("checkins", "domainid"):
            self.db.query(self.db.rewrite_sql("ALTER TABLE checkins ADD UNIQUE KEY `domainid` (`repositoryid`, `branchid`, `dirid`, `fileid`, `revision`)"), [])

        if not self.has_index("descs", "i_description"):
            try:
                self.db.query("CREATE FULLTEXT INDEX `i_description` ON `descs` (`description`)", [])
            except:
                print("WARN: Could not create fulltext index. MySQL version >= 5.6 required.")


    def create_database_structure(self):
        structure = """
ALTER DATABASE """ + self.config["db"]["database"] + """ CHARSET 'UTF8';
CREATE TABLE IF NOT EXISTS `branches` (
  `id` mediumint(9) NOT NULL AUTO_INCREMENT,
  `branch` varchar(200),
  PRIMARY KEY (`id`), UNIQUE KEY `branch` (`branch`)
);
CREATE TABLE IF NOT EXISTS `checkins` (
  `id` mediumint(9) NOT NULL AUTO_INCREMENT,
  `type` enum('Change','Add','Remove') DEFAULT NULL,
  `ci_when` datetime NOT NULL,
  `whoid` mediumint(9) NOT NULL,
  `repositoryid` mediumint(9) NOT NULL,
  `dirid` mediumint(9) NOT NULL,
  `fileid` mediumint(9) NOT NULL,
  `revision` char(50) DEFAULT NULL,
  `stickytag` varchar(255) NOT NULL,
  `branchid` mediumint(9) NOT NULL,
  `addedlines` int(11) NOT NULL,
  `removedlines` int(11) NOT NULL,
  `descid` mediumint(9) NOT NULL,
  `commitid` mediumint(9),
  PRIMARY KEY(`id`),
  UNIQUE KEY `domainid` (`repositoryid`, `branchid`, `dirid`, `fileid`, `revision`),
  KEY `ci_when` (`ci_when`),
  KEY `whoid` (`whoid`),
  KEY `repositoryid_2` (`repositoryid`),
  KEY `dirid` (`dirid`),
  KEY `fileid` (`fileid`),
  KEY `branchid` (`branchid`),
  KEY `descid` (`descid`)
);
CREATE TABLE IF NOT EXISTS `descs` (
  `id` mediumint(9) NOT NULL AUTO_INCREMENT,
  `description` text,
  `hash` bigint(20) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `hash` (`hash`)
);
CREATE TABLE IF NOT EXISTS `dirs` (
  `id` mediumint(9) NOT NULL AUTO_INCREMENT,
  `dir` varchar(254) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `dir` (`dir`)
);
CREATE TABLE IF NOT EXISTS `files` (
  `id` mediumint(9) NOT NULL AUTO_INCREMENT,
  `file` varchar(128) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `file` (`file`)
);
CREATE TABLE IF NOT EXISTS `people` (
  `id` mediumint(9) NOT NULL AUTO_INCREMENT,
  `who` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `who` (`who`)
);
CREATE TABLE IF NOT EXISTS `repositories` (
  `id` mediumint(9) NOT NULL AUTO_INCREMENT,
  `repository` varchar(64) NOT NULL,
  `base_url` varchar(255) DEFAULT NULL,
  `repository_url` varchar(255) DEFAULT NULL,
  `file_url` varchar(255) DEFAULT NULL,
  `commit_url` varchar(255) DEFAULT NULL,
  `tracker_url` varchar(255) DEFAULT NULL,
  `icon_url` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `repository` (`repository`)
);
CREATE TABLE IF NOT EXISTS `tags` (
  `id` mediumint(9) NOT NULL AUTO_INCREMENT,
  `repositoryid` mediumint(9) NOT NULL,
  `branchid` mediumint(9) NOT NULL,
  `dirid` mediumint(9) NOT NULL,
  `fileid` mediumint(9) NOT NULL,
  `revision` varchar(32) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `repositoryid` (`repositoryid`,`dirid`,`fileid`,`branchid`,`revision`),
  KEY `repositoryid_2` (`repositoryid`),
  KEY `dirid` (`dirid`),
  KEY `fileid` (`fileid`),
  KEY `branchid` (`branchid`)
);
CREATE TABLE IF NOT EXISTS `commitids` (
  `id` mediumint(9) NOT NULL AUTO_INCREMENT,
  `hash` varchar(60),
  `co_when` datetime NOT NULL,
  `authorid` mediumint(9) NOT NULL,
  `committerid` mediumint(9) NOT NULL,
  `remote_addr` varchar(255),
  `remote_user` varchar(255),
  PRIMARY KEY (`id`),
  UNIQUE KEY `hash` (`hash`)
)  
        """
        print("OK: Starting database structure check and update")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for sql in structure.split(";"):
                self.db.query(self.db.rewrite_sql(sql), [])

        self.convert_to_innodb()
        self.convert_to_utf8()
        self.update_database_structure()
        self.update_index_definitions()

        print("OK: Completed database structure check and update")

    @staticmethod
    def are_rows_in_same_commit(row, last_row):
        """checks whether the modifications belong to the same commit"""

        #id, ci_when, whoid, repositoryid, branchid, descid
        for i in range(2, 6):
            if (row[i] != last_row[i]):
                return False
        return True


    def synthesize_cvs_commit_ids(self):
        """generates cvs commitid for checkins without one"""

        rows = self.db.query(self.db.rewrite_sql("SELECT count(*) FROM checkins WHERE commitid IS NULL"), []);
        count = rows[0][0]
        if (count == 0):
            return

        print("Updating " + str(count) + " legacy CVS entries")
        select = self.db.rewrite_sql("SELECT id, ci_when, whoid, repositoryid, branchid, descid FROM checkins WHERE commitid IS NULL ORDER BY repositoryid, branchid, whoid, ci_when LIMIT 100000")
        rows = self.db.query(select, [])

        i = 0
        commitid = 0
        last_row = [0, 0, 0, 0, 0, 0]
        while len(rows) > 0:
            cursor = self.db.conn.cursor()
            for row in rows:
                if not self.are_rows_in_same_commit(row, last_row):
                    cursor.execute("INSERT INTO commitids (hash, co_when, authorid, committerid) VALUES (%s, %s, %s, %s)", ["s" + str(time.time()) + str(i), row[1], row[2], row[2]])
                    commitid = cursor.lastrowid
                cursor.execute(self.db.rewrite_sql("UPDATE checkins SET commitid=%s WHERE id=%s"), [commitid, row[0]])
                i = i + 1
                last_row = row

            cursor.close()
            self.db.conn.commit()
            self.db.conn.begin()
            print("    Updated " + str(i) + " / " + str(count))
            rows = self.db.query(select, []);
        cursor.close()
        self.db.conn.commit()
        print("OK: Converted CVS legacy entries")


    def main(self):
        self.import_config()
        self.check_db_config()
        self.connect()
        self.create_database_structure()
        self.synthesize_cvs_commit_ids()



if __name__ == '__main__':
    PostsaiInstaller().main()
