SET LOCAL lock_timeout = '5s';
ALTER TABLE storage_costs ALTER COLUMN chrtid TYPE BIGINT;
