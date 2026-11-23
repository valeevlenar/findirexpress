BEGIN;

CREATE TABLE marking_participants (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    inn varchar(12) NOT NULL UNIQUE,
    name text NOT NULL CHECK (btrim(name) <> ''),
    kind text NOT NULL CHECK (kind IN ('ip', 'company')),
    seller_id integer UNIQUE REFERENCES sellers(id),
    CHECK ((kind = 'ip' AND inn ~ '^[0-9]{12}$' AND seller_id IS NULL)
        OR (kind = 'company' AND inn ~ '^[0-9]{10}$'))
);

CREATE TABLE marking_access (
    participant_id bigint NOT NULL REFERENCES marking_participants(id),
    user_id integer NOT NULL REFERENCES users(id),
    role text NOT NULL CHECK (role IN ('viewer', 'operator', 'admin')),
    PRIMARY KEY (participant_id, user_id)
);

CREATE TABLE marking_routes (
    issuer_id bigint NOT NULL REFERENCES marking_participants(id),
    recipient_id bigint NOT NULL REFERENCES marking_participants(id),
    PRIMARY KEY (issuer_id, recipient_id),
    CHECK (issuer_id <> recipient_id)
);

CREATE TABLE marking_connections (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    participant_id bigint NOT NULL REFERENCES marking_participants(id),
    environment text NOT NULL CHECK (environment IN ('test', 'production')),
    oms_id text NOT NULL CHECK (btrim(oms_id) <> ''),
    UNIQUE (participant_id, environment),
    UNIQUE (id, participant_id, environment)
);

CREATE TABLE marking_orders (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id uuid NOT NULL UNIQUE,
    connection_id bigint NOT NULL,
    issuer_id bigint NOT NULL REFERENCES marking_participants(id),
    environment text NOT NULL CHECK (environment IN ('test', 'production')),
    product_group text NOT NULL,
    emission_method text NOT NULL,
    status text NOT NULL DEFAULT 'draft' CHECK (status IN (
        'draft', 'approved', 'submission_unknown', 'submitted', 'issued', 'received', 'rejected', 'cancelled'
    )),
    external_order_id text,
    created_by integer NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    approved_by integer REFERENCES users(id),
    approved_at timestamptz,
    CHECK ((approved_by IS NULL) = (approved_at IS NULL)),
    FOREIGN KEY (connection_id, issuer_id, environment)
        REFERENCES marking_connections(id, participant_id, environment),
    UNIQUE (connection_id, external_order_id),
    UNIQUE (id, environment)
);

CREATE TABLE marking_order_items (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL,
    environment text NOT NULL,
    gtin varchar(14) NOT NULL CHECK (gtin ~ '^[0-9]{14}$'),
    quantity integer NOT NULL CHECK (quantity > 0),
    FOREIGN KEY (order_id, environment) REFERENCES marking_orders(id, environment),
    UNIQUE (order_id, gtin),
    UNIQUE (id, environment, gtin)
);

CREATE TABLE marking_codes (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_item_id bigint NOT NULL,
    environment text NOT NULL,
    gtin varchar(14) NOT NULL,
    serial text NOT NULL CHECK (length(serial) > 0),
    encrypted_code bytea NOT NULL CHECK (octet_length(encrypted_code) > 0),
    encryption_key_id text NOT NULL CHECK (btrim(encryption_key_id) <> ''),
    issued_at timestamptz,
    received_at timestamptz NOT NULL DEFAULT now(),
    owner_id bigint NOT NULL REFERENCES marking_participants(id),
    FOREIGN KEY (order_item_id, environment, gtin)
        REFERENCES marking_order_items(id, environment, gtin),
    UNIQUE (environment, gtin, serial),
    UNIQUE (id, environment)
);

CREATE TABLE marking_transfers (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id uuid NOT NULL UNIQUE,
    environment text NOT NULL CHECK (environment IN ('test', 'production')),
    sender_id bigint NOT NULL,
    recipient_id bigint NOT NULL,
    status text NOT NULL DEFAULT 'draft' CHECK (status IN (
        'draft', 'sent', 'signed', 'confirmed', 'rejected', 'cancelled'
    )),
    edo_provider text,
    edo_document_id text,
    gismt_document_id text,
    created_by integer NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    confirmed_at timestamptz,
    FOREIGN KEY (sender_id, recipient_id) REFERENCES marking_routes(issuer_id, recipient_id),
    CHECK (edo_document_id IS NULL OR edo_provider IS NOT NULL),
    CHECK ((status = 'confirmed') = (confirmed_at IS NOT NULL)),
    CHECK (status <> 'confirmed' OR gismt_document_id IS NOT NULL),
    UNIQUE (environment, sender_id, edo_provider, edo_document_id),
    UNIQUE (environment, gismt_document_id),
    UNIQUE (id, environment)
);

CREATE TABLE marking_transfer_codes (
    transfer_id bigint NOT NULL,
    code_id bigint NOT NULL,
    environment text NOT NULL,
    reserved_at timestamptz NOT NULL DEFAULT now(),
    released_at timestamptz,
    CHECK (released_at IS NULL OR released_at >= reserved_at),
    PRIMARY KEY (transfer_id, code_id),
    FOREIGN KEY (transfer_id, environment) REFERENCES marking_transfers(id, environment),
    FOREIGN KEY (code_id, environment) REFERENCES marking_codes(id, environment)
);

CREATE UNIQUE INDEX marking_one_active_transfer_per_code
    ON marking_transfer_codes (code_id) WHERE released_at IS NULL;

CREATE TABLE marking_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code_id bigint NOT NULL,
    environment text NOT NULL,
    transfer_id bigint,
    event_type text NOT NULL CHECK (event_type IN (
        'issued', 'received', 'applied', 'introduced', 'transfer_reserved', 'transfer_sent',
        'transfer_signed', 'transfer_confirmed', 'transfer_rejected', 'transfer_cancelled', 'correction'
    )),
    source text NOT NULL CHECK (source IN ('findirexpress', 'suz', 'gismt', 'edo')),
    source_event_id text NOT NULL CHECK (btrim(source_event_id) <> ''),
    actor_user_id integer REFERENCES users(id),
    occurred_at timestamptz,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (code_id, environment) REFERENCES marking_codes(id, environment),
    FOREIGN KEY (transfer_id, code_id) REFERENCES marking_transfer_codes(transfer_id, code_id),
    CHECK (event_type NOT LIKE 'transfer_%' OR transfer_id IS NOT NULL),
    CHECK (event_type <> 'transfer_confirmed' OR source = 'gismt'),
    UNIQUE (code_id, source, source_event_id, event_type)
);

CREATE FUNCTION marking_reject_event_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Marking history is append-only';
END;
$$;

CREATE TRIGGER marking_events_append_only
    BEFORE UPDATE OR DELETE OR TRUNCATE ON marking_events
    FOR EACH STATEMENT EXECUTE FUNCTION marking_reject_event_mutation();

COMMIT;
