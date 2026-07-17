begin;

alter table public.facilities enable row level security;
alter table public.departments enable row level security;
alter table public.specialties enable row level security;
alter table public.medical_services enable row level security;
alter table public.doctors enable row level security;
alter table public.patients enable row level security;
alter table public.user_accounts enable row level security;
alter table public.patient_insurances enable row level security;
alter table public.doctor_schedules enable row level security;
alter table public.appointment_slots enable row level security;
alter table public.appointments enable row level security;
alter table public.appointment_histories enable row level security;
alter table public.service_prices enable row level security;
alter table public.invoices enable row level security;
alter table public.payments enable row level security;
alter table public.knowledge_documents enable row level security;
alter table public.knowledge_chunks enable row level security;
alter table public.intent_catalog enable row level security;
alter table public.agent_workflows enable row level security;
alter table public.conversation_sessions enable row level security;
alter table public.conversation_messages enable row level security;
alter table public.support_tickets enable row level security;
alter table public.audit_logs enable row level security;

create function public.current_patient_id() returns text language sql stable security definer set search_path = public as $$
  select patient_id from public.user_accounts where auth_user_id = auth.uid() and account_status = 'ACTIVE' limit 1
$$;

create policy "public reads facilities" on public.facilities for select to anon, authenticated using (current_operational_status = 'ACTIVE');
create policy "public reads departments" on public.departments for select to anon, authenticated using (status = 'ACTIVE');
create policy "public reads specialties" on public.specialties for select to anon, authenticated using (status = 'ACTIVE');
create policy "public reads services" on public.medical_services for select to anon, authenticated using (service_status = 'ACTIVE');
create policy "public reads doctors" on public.doctors for select to anon, authenticated using (doctor_status = 'ACTIVE');
create policy "public reads schedules" on public.doctor_schedules for select to anon, authenticated using (schedule_status = 'OPEN');
create policy "public reads available slots" on public.appointment_slots for select to anon, authenticated using (slot_status = 'AVAILABLE');
create policy "public reads approved prices" on public.service_prices for select to anon, authenticated using (approval_status = 'APPROVED');
create policy "public reads approved knowledge" on public.knowledge_documents for select to anon, authenticated using (approval_status = 'APPROVED' and (effective_to is null or effective_to >= current_date));
create policy "public reads knowledge chunks" on public.knowledge_chunks for select to anon, authenticated using (access_level = 'PUBLIC' and (effective_to is null or effective_to >= current_date));

create policy "patient reads own profile" on public.patients for select to authenticated using (patient_id = public.current_patient_id());
create policy "patient updates own profile" on public.patients for update to authenticated using (patient_id = public.current_patient_id()) with check (patient_id = public.current_patient_id());
create policy "user reads own account" on public.user_accounts for select to authenticated using (auth_user_id = auth.uid());
create policy "patient reads own insurance" on public.patient_insurances for select to authenticated using (patient_id = public.current_patient_id());
create policy "patient reads own appointments" on public.appointments for select to authenticated using (patient_id = public.current_patient_id());
create policy "patient creates own appointments" on public.appointments for insert to authenticated with check (patient_id = public.current_patient_id());
create policy "patient updates own appointments" on public.appointments for update to authenticated using (patient_id = public.current_patient_id()) with check (patient_id = public.current_patient_id());
create policy "patient reads own invoices" on public.invoices for select to authenticated using (patient_id = public.current_patient_id());
create policy "patient reads own payments" on public.payments for select to authenticated using (patient_id = public.current_patient_id());
create policy "user reads own sessions" on public.conversation_sessions for select to authenticated using (patient_id = public.current_patient_id());
create policy "user reads own messages" on public.conversation_messages for select to authenticated using (exists (select 1 from public.conversation_sessions s where s.session_id = conversation_messages.session_id and s.patient_id = public.current_patient_id()));
create policy "patient reads own tickets" on public.support_tickets for select to authenticated using (patient_id = public.current_patient_id());

create or replace function public.book_appointment(
  p_appointment_id text, p_appointment_code text, p_patient_id text, p_slot_id text,
  p_service_id text, p_reason text default null
) returns public.appointments
language plpgsql security definer set search_path = public as $$
declare v_slot public.appointment_slots; v_schedule public.doctor_schedules; v_result public.appointments;
begin
  if auth.role() <> 'service_role' and p_patient_id <> public.current_patient_id() then raise exception 'forbidden' using errcode = '42501'; end if;
  select * into v_slot from public.appointment_slots where slot_id = p_slot_id for update;
  if not found or v_slot.slot_status <> 'AVAILABLE' then raise exception 'slot_unavailable' using errcode = 'P0001'; end if;
  select * into v_schedule from public.doctor_schedules where schedule_id = v_slot.schedule_id;
  if not (v_schedule.service_ids ? p_service_id) then raise exception 'service_not_in_schedule' using errcode = 'P0001'; end if;
  insert into public.appointments(appointment_id,appointment_code,patient_id,facility_id,department_id,service_id,doctor_id,slot_id,
    appointment_datetime,consultation_mode,booking_channel,booking_source,reason_for_visit,priority_level,appointment_status,confirmation_status,mock_scenario)
  values(p_appointment_id,p_appointment_code,p_patient_id,v_schedule.facility_id,v_schedule.department_id,p_service_id,v_schedule.doctor_id,p_slot_id,
    v_slot.start_datetime,v_schedule.consultation_mode,'SUPABASE_RPC','AI_AGENT',p_reason,'NORMAL','CONFIRMED','CONFIRMED','API_TEST') returning * into v_result;
  update public.appointment_slots set slot_status='BOOKED',booked_count=booked_count+1,appointment_id=p_appointment_id where slot_id=p_slot_id;
  insert into public.appointment_histories(history_id,appointment_id,action_type,new_value,changed_by,change_channel,changed_at,mock_scenario)
  values('HIS-'||p_appointment_id,p_appointment_id,'CREATED',jsonb_build_object('status','CONFIRMED'),'ai_agent','SUPABASE_RPC',now(),'API_TEST');
  return v_result;
end $$;

grant execute on function public.book_appointment(text,text,text,text,text,text) to authenticated, service_role;

commit;
