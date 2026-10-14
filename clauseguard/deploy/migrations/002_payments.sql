create table if not exists claim_payments_log (
    id text primary key,
    claim_id text not null,
    payer text,
    amount bigint not null,
    paid_date date,
    updated_at timestamptz not null default now()
);

alter table claim_payments_log enable row level security;
revoke all on claim_payments_log from anon, authenticated;
