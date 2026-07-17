begin;

create extension if not exists pgcrypto;

create type public.appointment_status as enum ('PENDING','CONFIRMED','COMPLETED','CANCELLED','NO_SHOW');
create type public.slot_status as enum ('AVAILABLE','HELD','BOOKED','BLOCKED');
create type public.payment_status as enum ('PENDING','SUCCESS','FAILED','REFUNDED');
create type public.session_status as enum ('ACTIVE','COMPLETED','ABANDONED','HANDED_OVER');

create table public.facilities (
  facility_id text primary key, facility_code text not null unique, facility_name text not null,
  facility_type text not null check (facility_type in ('HOSPITAL','CLINIC','LAB_CENTER')),
  address text not null, province text not null, district text, latitude numeric(9,6), longitude numeric(9,6),
  hotline text not null, email text, website text, operating_hours jsonb not null default '{}', emergency_available boolean not null default false,
  accessibility_support jsonb not null default '[]', current_operational_status text not null default 'ACTIVE',
  mock_scenario text not null default 'SUCCESS', metadata jsonb not null default '{}'
);

create table public.departments (
  department_id text primary key, facility_id text not null references public.facilities on delete restrict,
  department_code text not null unique, department_name text not null, department_type text not null,
  specialty_group text, description text, location_building text, location_floor integer, room_number text,
  operating_hours jsonb not null default '{}', appointment_required boolean not null default true, status text not null default 'ACTIVE',
  mock_scenario text not null default 'SUCCESS', metadata jsonb not null default '{}'
);

create table public.specialties (
  specialty_id text primary key, specialty_code text not null unique, specialty_name text not null, description text,
  common_symptoms jsonb not null default '[]', excluded_conditions jsonb not null default '[]', age_group jsonb not null default '[]',
  related_department_ids jsonb not null default '[]', triage_priority text, emergency_warning jsonb not null default '[]', status text not null default 'ACTIVE',
  mock_scenario text not null default 'SUCCESS', metadata jsonb not null default '{}'
);

create table public.medical_services (
  service_id text primary key, service_code text not null unique, service_name text not null,
  service_category text not null check (service_category in ('CONSULTATION','LAB_TEST','IMAGING','PROCEDURE','CHECKUP_PACKAGE')),
  department_id text not null references public.departments on delete restrict, facility_ids jsonb not null default '[]', description text,
  target_patient_group text, booking_required boolean not null, doctor_required boolean not null, estimated_duration_minutes integer not null check (estimated_duration_minutes > 0),
  preparation_instructions text, required_documents jsonb not null default '[]', result_turnaround_time text, result_delivery_methods jsonb not null default '[]',
  base_price numeric(14,2) not null check (base_price >= 0), price_min numeric(14,2) check (price_min >= 0), price_max numeric(14,2) check (price_max >= 0),
  insurance_supported boolean not null default false, insurance_notes text, service_status text not null default 'ACTIVE', mock_scenario text not null default 'SUCCESS', metadata jsonb not null default '{}'
);

create table public.doctors (
  doctor_id text primary key, employee_code text not null unique, full_name text not null, title text, professional_position text,
  specialty_ids jsonb not null default '[]', department_id text not null references public.departments on delete restrict,
  facility_ids jsonb not null default '[]', years_of_experience integer not null check (years_of_experience >= 0), professional_profile text,
  languages jsonb not null default '[]', consultation_modes jsonb not null default '[]', patient_age_groups jsonb not null default '[]',
  average_consultation_minutes integer, rating numeric(2,1) check (rating between 1 and 5),
  doctor_status text not null check (doctor_status in ('ACTIVE','ON_LEAVE','NOT_ACCEPTING_APPOINTMENTS')),
  mock_scenario text not null default 'SUCCESS', metadata jsonb not null default '{}'
);

create table public.patients (
  patient_id text primary key, patient_code text not null unique, full_name text not null, date_of_birth date not null, gender text not null,
  nationality text, phone_number text, email text, identity_type text, identity_number_masked text, address text, province text,
  preferred_language text not null default 'vi', preferred_channel text, accessibility_needs jsonb not null default '[]',
  emergency_contact_name text, emergency_contact_phone text, guardian_patient_id text references public.patients on delete set null,
  is_minor boolean not null, profile_status text not null, last_visit_date date, blood_type text, allergy_summary text,
  chronic_condition_summary text, mobility_support_required boolean not null default false, pregnancy_status text,
  mock_scenario text not null default 'SUCCESS', metadata jsonb not null default '{}', created_at timestamptz not null default now()
);

create table public.user_accounts (
  user_id text primary key, auth_user_id uuid unique references auth.users on delete set null,
  patient_id text references public.patients on delete cascade, username text not null unique, login_phone text, login_email text,
  role text not null, authentication_provider text, account_status text not null, mfa_enabled boolean not null default false,
  last_login_at timestamptz, failed_login_count integer not null default 0, password_reset_required boolean not null default false,
  terms_accepted_at timestamptz, privacy_policy_version text, mock_scenario text not null default 'SUCCESS', metadata jsonb not null default '{}'
);

create table public.patient_insurances (
  insurance_id text primary key, patient_id text not null references public.patients on delete cascade,
  insurance_type text not null check (insurance_type in ('BHYT','PRIVATE','NONE')), provider_name text, insurance_number_masked text,
  plan_name text, valid_from date, valid_to date, registration_facility text references public.facilities on delete set null,
  coverage_percentage numeric(5,2) check (coverage_percentage between 0 and 100), referral_required boolean not null default false,
  referral_status text, eligibility_status text not null, verification_status text, verified_at timestamptz, verification_message text,
  document_ids jsonb not null default '[]', mock_scenario text not null default 'SUCCESS', metadata jsonb not null default '{}'
);

create table public.doctor_schedules (
  schedule_id text primary key, doctor_id text not null references public.doctors on delete cascade,
  facility_id text not null references public.facilities on delete restrict, department_id text not null references public.departments on delete restrict,
  service_ids jsonb not null default '[]', schedule_date date not null, start_time time not null, end_time time not null,
  slot_duration_minutes integer not null check (slot_duration_minutes > 0), maximum_patients integer not null check (maximum_patients > 0),
  consultation_mode text not null, room_number text, schedule_status text not null, allow_overbooking boolean not null default false,
  schedule_notes text, mock_scenario text not null default 'SUCCESS', metadata jsonb not null default '{}', check (end_time > start_time)
);

create table public.appointment_slots (
  slot_id text primary key, schedule_id text not null references public.doctor_schedules on delete cascade,
  start_datetime timestamptz not null, end_datetime timestamptz not null, slot_status public.slot_status not null,
  capacity integer not null default 1 check (capacity > 0), booked_count integer not null default 0 check (booked_count >= 0),
  hold_session_id text, hold_expires_at timestamptz, appointment_id text, blocking_reason text,
  mock_scenario text not null default 'SUCCESS', metadata jsonb not null default '{}',
  check (end_datetime > start_datetime), check (booked_count <= capacity),
  check (slot_status <> 'HELD' or (hold_session_id is not null and hold_expires_at is not null)),
  check (slot_status <> 'BLOCKED' or blocking_reason is not null)
);

create table public.appointments (
  appointment_id text primary key, appointment_code text not null unique, patient_id text not null references public.patients on delete restrict,
  facility_id text not null references public.facilities on delete restrict, department_id text not null references public.departments on delete restrict,
  service_id text not null references public.medical_services on delete restrict, doctor_id text references public.doctors on delete restrict,
  slot_id text not null unique, appointment_datetime timestamptz not null,
  consultation_mode text not null, booking_channel text, booking_source text not null, reason_for_visit text, symptom_summary text,
  priority_level text not null, appointment_status public.appointment_status not null, confirmation_status text, checkin_status text,
  payment_status text, insurance_usage boolean not null default false, required_documents_status text, special_request text,
  cancellation_reason text, cancelled_at timestamptz, rescheduled_from_id text references public.appointments on delete set null,
  created_by_agent boolean not null default false, mock_scenario text not null default 'SUCCESS', metadata jsonb not null default '{}',
  created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
  check (appointment_status <> 'CANCELLED' or (cancelled_at is not null and cancellation_reason is not null))
);
alter table public.appointments add constraint appointments_slot_fk foreign key (slot_id) references public.appointment_slots on delete restrict deferrable initially deferred;
alter table public.appointment_slots add constraint appointment_slots_appointment_fk foreign key (appointment_id) references public.appointments on delete set null deferrable initially deferred;

create table public.appointment_histories (
  history_id text primary key, appointment_id text not null references public.appointments on delete cascade,
  action_type text not null, old_value jsonb, new_value jsonb, changed_by text, change_channel text, change_reason text,
  changed_at timestamptz not null, mock_scenario text not null default 'SUCCESS', metadata jsonb not null default '{}'
);

create table public.service_prices (
  price_id text primary key, service_id text not null references public.medical_services on delete cascade,
  facility_id text not null references public.facilities on delete cascade, patient_category text not null,
  price_amount numeric(14,2) not null check (price_amount >= 0), currency text not null default 'VND', effective_from date not null,
  effective_to date, insurance_covered_amount numeric(14,2) not null check (insurance_covered_amount >= 0),
  patient_pay_amount numeric(14,2) not null check (patient_pay_amount >= 0), price_note text, approval_status text not null,
  mock_scenario text not null default 'SUCCESS', metadata jsonb not null default '{}'
);

create table public.invoices (
  invoice_id text primary key, invoice_code text not null unique, patient_id text not null references public.patients on delete restrict,
  appointment_id text references public.appointments on delete set null, encounter_id text, issued_at timestamptz not null,
  subtotal_amount numeric(14,2) not null check (subtotal_amount >= 0), discount_amount numeric(14,2) not null check (discount_amount >= 0),
  insurance_amount numeric(14,2) not null check (insurance_amount >= 0), patient_amount numeric(14,2) not null check (patient_amount >= 0),
  paid_amount numeric(14,2) not null check (paid_amount >= 0), remaining_amount numeric(14,2) not null check (remaining_amount >= 0),
  currency text not null default 'VND', invoice_status text not null, payment_due_at timestamptz, invoice_line_items jsonb not null default '[]',
  invoice_file_url text, mock_scenario text not null default 'SUCCESS', metadata jsonb not null default '{}',
  check (remaining_amount = greatest(patient_amount - paid_amount, 0)), check (invoice_status <> 'PAID' or remaining_amount = 0)
);

create table public.payments (
  payment_id text primary key, invoice_id text not null references public.invoices on delete restrict,
  patient_id text not null references public.patients on delete restrict, payment_method text, payment_provider text,
  transaction_reference text not null unique, amount numeric(14,2) not null check (amount >= 0), payment_status public.payment_status not null,
  paid_at timestamptz, failure_code text, failure_message text, refund_amount numeric(14,2) not null default 0 check (refund_amount >= 0),
  refunded_at timestamptz, mock_scenario text not null default 'SUCCESS', metadata jsonb not null default '{}'
);

create table public.knowledge_documents (
  knowledge_document_id text primary key, title text not null, document_type text, content text not null, summary text,
  department_ids jsonb not null default '[]', facility_ids jsonb not null default '[]', service_ids jsonb not null default '[]', language text not null,
  keywords jsonb not null default '[]', owner_department text, document_version integer not null, effective_from date, effective_to date,
  approval_status text not null, review_due_date date, source_reference text, risk_level text, allowed_response_scope text,
  mock_scenario text not null default 'SUCCESS', metadata jsonb not null default '{}'
);

create table public.knowledge_chunks (
  chunk_id text primary key, knowledge_document_id text not null references public.knowledge_documents on delete cascade,
  chunk_index integer not null, chunk_title text, chunk_content text not null, token_count integer, keywords jsonb not null default '[]',
  embedding_id text, department_ids jsonb not null default '[]', facility_ids jsonb not null default '[]', effective_from date, effective_to date,
  access_level text, citation_text text, mock_scenario text not null default 'SUCCESS', metadata jsonb not null default '{}',
  unique (knowledge_document_id, chunk_index)
);

create table public.intent_catalog (
  intent_id text primary key, intent_name text not null unique, display_name text, description text, intent_category text,
  sample_utterances jsonb not null default '[]', negative_examples jsonb not null default '[]', required_entities jsonb not null default '[]',
  optional_entities jsonb not null default '[]', workflow_id text, authentication_required boolean not null default false,
  risk_level text, human_handover_required boolean not null default false, fallback_intent_id text references public.intent_catalog,
  minimum_confidence numeric(4,3), active boolean not null default true, mock_scenario text not null default 'SUCCESS', metadata jsonb not null default '{}'
);

create table public.agent_workflows (
  workflow_id text primary key, workflow_name text not null, trigger_intent_id text not null references public.intent_catalog,
  description text, required_inputs jsonb not null default '[]', optional_inputs jsonb not null default '[]', authentication_level text,
  workflow_steps jsonb not null default '[]', allowed_tools jsonb not null default '[]', success_condition text, failure_condition text,
  timeout_seconds integer, maximum_retries integer, human_approval_required boolean not null default false, fallback_action text,
  risk_level text, workflow_version integer not null, mock_scenario text not null default 'SUCCESS', metadata jsonb not null default '{}'
);
alter table public.intent_catalog add constraint intent_workflow_fk foreign key (workflow_id) references public.agent_workflows deferrable initially deferred;

create table public.conversation_sessions (
  session_id text primary key, conversation_code text not null unique, user_id text references public.user_accounts on delete set null,
  patient_id text references public.patients on delete set null, anonymous_user_id text, channel text not null, entry_point text, language text,
  started_at timestamptz not null, ended_at timestamptz, session_status public.session_status not null, authentication_status text,
  current_intent_id text references public.intent_catalog, current_workflow_id text references public.agent_workflows,
  conversation_summary text, resolution_status text, handover_status text, assigned_agent_id text, user_sentiment text,
  csat_score integer check (csat_score between 1 and 5), model_version text, mock_scenario text not null default 'SUCCESS', metadata jsonb not null default '{}'
);

create table public.conversation_messages (
  message_id text primary key, session_id text not null references public.conversation_sessions on delete cascade,
  sequence_number integer not null check (sequence_number > 0), sender_type text not null, sender_id text, message_content text not null,
  message_type text not null, sent_at timestamptz not null, detected_intent_id text references public.intent_catalog,
  intent_confidence numeric(4,3), detected_entities jsonb not null default '[]', sentiment text, language text,
  pii_detected boolean not null default false, medical_risk_flag boolean not null default false, safety_flag boolean not null default false,
  source_chunk_ids jsonb not null default '[]', response_latency_ms integer, model_name text, prompt_version text, user_feedback text,
  error_code text, mock_scenario text not null default 'SUCCESS', metadata jsonb not null default '{}', unique(session_id, sequence_number)
);

create table public.support_tickets (
  ticket_id text primary key, ticket_code text not null unique, session_id text references public.conversation_sessions on delete set null,
  patient_id text references public.patients on delete set null, ticket_category text, subcategory text, title text not null, description text,
  conversation_summary text, priority text, assigned_team text, assigned_staff_id text, ticket_status text, sla_due_at timestamptz,
  resolution_content text, resolution_code text, closed_at timestamptz, reopened_count integer not null default 0,
  customer_satisfaction_score integer check (customer_satisfaction_score between 1 and 5), mock_scenario text not null default 'SUCCESS', metadata jsonb not null default '{}'
);

create table public.audit_logs (
  audit_id text primary key, actor_type text not null, actor_id text, action text not null, resource_type text not null,
  resource_id text, action_timestamp timestamptz not null, session_id text references public.conversation_sessions on delete set null,
  ip_address_masked text, device_id text, old_value jsonb, new_value jsonb, result text, reason text, risk_flag boolean not null default false,
  mock_scenario text not null default 'SUCCESS', metadata jsonb not null default '{}'
);

create index departments_facility_idx on public.departments(facility_id);
create index services_department_idx on public.medical_services(department_id);
create index doctors_department_idx on public.doctors(department_id);
create index schedules_lookup_idx on public.doctor_schedules(facility_id, doctor_id, schedule_date) where schedule_status = 'OPEN';
create index slots_available_idx on public.appointment_slots(schedule_id, start_datetime) where slot_status = 'AVAILABLE';
create index appointments_patient_time_idx on public.appointments(patient_id, appointment_datetime desc);
create index invoices_patient_idx on public.invoices(patient_id, issued_at desc);
create index messages_session_sequence_idx on public.conversation_messages(session_id, sequence_number);
create index chunks_document_idx on public.knowledge_chunks(knowledge_document_id, chunk_index);
create index tickets_status_sla_idx on public.support_tickets(ticket_status, sla_due_at);

commit;
