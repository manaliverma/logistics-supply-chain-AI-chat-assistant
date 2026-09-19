# Southern California Logistics Operations

## Standard Operating Procedure (SOP): Cold-Chain & Transit Anomalies

**Version:** 2.4 | **Effective Date:** Jan 2021 | **Confidentiality:** Internal Operations Only

### 1. Temperature Control & Spoilage Prevention (Cold-Chain)

All refrigerated fleets must maintain strict IoT temperature compliance to prevent cargo spoilage.

- **Perishable goods:** Products that require controlled temperature, humidity,
  handling, or transit time to prevent spoilage, contamination, quality loss,
  or regulatory non-compliance. This includes seafood, fish, shrimp, crab,
  lobster, shellfish, meat, poultry, dairy, eggs, fresh fruits, vegetables,
  leafy greens, berries, flowers, frozen foods, ice cream, fresh juices,
  prepared meals, vaccines, insulin, blood products, and other
  temperature-sensitive pharmaceuticals.
- **Fresh Perishables:** IoT temperature must remain between 0.0°C and 4.0°C.
- **Critical Breach:** If `IOT_TEMP_VAL_C` exceeds **4.0°C**, an immediate cold-chain breach is declared.
- **Mitigation Protocol:** The dispatcher must immediately contact the driver to restart the auxiliary cooling unit. If ETA delay is greater than 1 hour, divert the vehicle to the nearest emergency cold-storage facility.
- **Product-specific limits:** Frozen products and pharmaceuticals may require
  different validated temperature ranges. The product-specific storage
  requirement takes priority over the default 0.0°C to 4.0°C range.

### 1.1 Temperature-Impact Scenarios

The following conditions may cause a temperature breach or reduce cargo
quality:

- Seasonal heat waves, heat spikes, or unusually high ambient temperatures.
- Refrigeration unit failure or low fuel.
- Vehicle power loss while parked.
- Reefer door left open or opened too frequently.
- Poor insulation or damaged container seals.
- Temperature sensor failure or calibration error.
- Reefer plug unavailable at a port or warehouse.
- Excessive loading time in hot weather.
- Cargo packed too tightly, blocking airflow.
- Incorrect temperature set point.
- Delayed customs inspection or security screening.
- Power outage at a cold-storage facility.
- Trailer or container left in direct sunlight.
- Unplanned route diversion or traffic delay.

When any of these conditions is reported, the dispatcher must verify the
sensor reading, inspect the equipment or operating condition where possible,
record the exposure duration, and determine whether emergency cold storage is
required.

### 1.2 Weather and Environmental Controls

Weather conditions must be monitored before dispatch and throughout transit.
The Area Manager must use the official weather or emergency-management
assessment for the operating region and must not dispatch into unsafe
conditions.

- **Seasonal heat spike or heat wave:** Pre-cool the reefer, verify fuel,
  battery, set point, insulation, seals, and backup power, reduce door-open
  time, stage chilled cargo in cold storage, and add temperature checks at
  dispatch, handoff, and arrival.
- **Extreme heat with traffic or a port queue:** Do not leave a reefer
  stationary without confirmed power. Move the shipment to powered cold
  storage or an approved safe location and recalculate the exposure window and
  ETA.
- **Flooding or flash flood:** Stop dispatch through the affected route, move
  vehicles and cargo to higher safe ground, protect electrical and cooling
  equipment, confirm an alternate route and receiving capacity, and inspect
  cargo before resuming movement.
- **Severe storm, lightning, or high winds:** Pause exposed yard, dock, crane,
  and linehaul activity when safety guidance requires it. Secure freight,
  equipment, and doors, then resume only after the authorized safety clearance.
- **Wildfire, smoke, or evacuation:** Follow evacuation or shelter orders,
  close affected operations, move cargo only when safe, and coordinate an
  alternate facility or cold-storage location.
- **Earthquake or structural event:** Stop operations, account for people,
  inspect the facility, utilities, racks, trailers, and cargo, and do not
  resume until safety clearance is issued.
- **Power outage:** Protect refrigerated inventory with generators, shore
  power, or a powered backup facility. Record the outage start time and
  temperature trend and escalate before the product exposure limit is reached.
- **Extreme cold, snow, or ice:** Prevent freezing damage, confirm road
  safety, protect exposed equipment and cargo, and use the product-specific
  minimum temperature.

### 1.3 Combined and Cascading Risk Scenarios

Multiple moderate conditions can create a critical incident. The Area Manager
must treat the combined operational impact as higher than any single trigger
when conditions interact.

Examples include:

- Heat wave + traffic congestion or port queue.
- Port congestion + reefer plug shortage.
- Flooding + road closure + missed warehouse appointment.
- Wildfire or smoke + route diversion + extended temperature exposure.
- Storm or power outage + cold-storage capacity shortage.
- Customs hold + high ambient temperature + refrigerated cargo.
- Vehicle breakdown + driver hours-of-service limit + perishable shipment.
- High port congestion + `RISK_CLS_TXT = High Risk` +
  `DELAY_PROB_DEC > 0.65`.
- Sensor failure + suspected refrigeration failure, where the true temperature
  cannot be confirmed.
- Depot or cross-dock capacity limit + active customer promise or temperature
  window.

For a combined event, the Area Manager must:

1. Make people and the site safe before moving freight.
2. Identify every active trigger and the worst credible outcome.
3. Apply the strictest applicable product, safety, and exposure requirement.
4. Stop or divert movement when the destination, route, power, or cold-storage
   control is not confirmed.
5. Assign an incident owner, backup plan, and next update time.
6. Escalate immediately when a temperature window, regulatory requirement,
   customer promise, or life-safety condition is threatened.
7. Record each contributing condition separately so the root cause is not
   hidden under a generic "weather delay" label.

### 2. Route Congestion & Diversion Tactics

Port congestion heavily impacts SLA compliance.

- **Port of Long Beach / LA:** If port congestion level (`PRT_CNG_LVL`) exceeds a severity index of **7.0**, standard routing is suspended.
- **Mitigation Protocol:** Do not hold freight at the port. Divert all active shipments to the **Inland Empire Overflow Depot (San Bernardino)** for cross-docking.

### 3. Risk Classification Triggers

Any shipment classified as **"High Risk"** (`RISK_CLS_TXT` = `High Risk`) combined with a delay probability (`DELAY_PROB_DEC`) greater than **0.65** must be escalated to the Tier 2 Logistics Manager.

### 4. Port-Delay Scenarios

The following scenarios must be treated as port-delay incidents:

- **Terminal congestion:** Long truck queues, limited gate appointments, or container-handling backlogs.
- **Vessel or berth delay:** A vessel cannot dock or unload according to its scheduled arrival.
- **Customs or inspection hold:** Freight cannot be released because of documentation, inspection, or clearance requirements.
- **Equipment shortage:** A shortage of chassis, trucks, containers, cranes, or labor prevents cargo movement.
- **Rail or road disruption:** A downstream rail connection, highway, or transfer route is unavailable.
- **Weather or safety closure:** Port operations are reduced or suspended because of severe weather or unsafe conditions.

When a port-delay scenario is confirmed, the dispatcher must validate the shipment status with the terminal or carrier, record the expected delay, and update the ETA. If the delay affects a refrigerated shipment, the dispatcher must also verify remaining cold-storage capacity and monitor `IOT_TEMP_VAL_C`.

### 5. Area Manager Command Responsibilities

The Area Manager owns the operational response across the fulfillment center,
yard, port, carriers, linehaul, delivery stations, and emergency storage
partners. The Area Manager must:

1. Protect people, product, and regulatory compliance before protecting speed.
2. Establish one incident owner and one communication channel.
3. Verify facts using sensor data, carrier or terminal updates, and physical
   checks instead of relying on an unverified status.
4. Prioritize shipments by safety risk, temperature exposure, customer impact,
   and promised delivery time.
5. Assign labor, dock doors, equipment, cold-storage space, and alternate
   transportation.
6. Maintain an incident log and scheduled updates until closure.
7. Complete a handoff and after-action review for every critical incident.

No shipment may be released, rerouted, or marked delivered to conceal a delay,
temperature breach, damaged package, missing documentation, or failed handoff.

### 6. Condition-Based Response Playbook

Use this sequence for every event:

```text
Detect → Make safe → Verify → Classify → Contain → Recover → Communicate → Close
```

#### 6.1 Immediate safety or security event

For fire, hazardous-material release, serious injury, active security threat,
vehicle collision, natural disaster, or unsafe facility conditions:

- Stop the affected operation and protect people first.
- Contact emergency services and the site safety or security owner.
- Isolate the area and prevent unauthorized freight movement.
- Account for associates, drivers, visitors, and carriers.
- Preserve evidence and record the time, location, and decision owner.
- Resume operations only after authorized safety or security clearance.

#### 6.2 Temperature above the product maximum

- Treat the shipment as a cold-chain incident immediately.
- Do not ship, stow, pick, or deliver it until disposition is approved.
- Verify the reading and check the reefer, power, fuel, doors, seals, set
  point, and handling history.
- Record the highest temperature and exposure duration.
- Move the shipment to validated cold storage or a backup powered reefer.
- Contact the carrier, quality owner, and Tier 2 Logistics Manager.
- Release, rework, return, or dispose of product only under approved quality
  or regulatory direction.

#### 6.3 Temperature below the product minimum

- Check for freezing damage, incorrect set point, sensor error, and blocked
  airflow.
- Segregate cargo that could be damaged by freezing.
- Move it to the validated range and obtain quality disposition.
- Do not assume that a low temperature is safe.

#### 6.4 Refrigeration, power, reefer, or sensor failure

- Contact the driver or facility owner and restart auxiliary cooling when safe.
- Check fuel, battery, shore power, reefer plug, seals, insulation, and airflow.
- Use a calibrated backup sensor when the primary sensor is questionable.
- Transfer cargo to emergency cold storage if recovery is not confirmed
  promptly or the exposure limit may be exceeded.
- Record the fault and repair the asset before returning it to service.

#### 6.5 Port congestion or port delay

- **Normal (`PRT_CNG_LVL <= 3.0`):** Continue routing, monitor the next
  appointment, and confirm the ETA.
- **Elevated (`3.0 < PRT_CNG_LVL <= 7.0`):** Contact the terminal or carrier,
  secure an alternate appointment, estimate the delay, notify downstream
  facilities, and prepare an alternate route.
- **Critical (`PRT_CNG_LVL > 7.0`):** Suspend standard routing, do not hold
  freight at the port, and divert active shipments to the Inland Empire
  Overflow Depot for cross-docking.

For terminal queues, canceled appointments, vessel or berth delays, customs
holds, documentation mismatches, equipment shortages, labor or system
outages, rail or road disruptions, weather closures, carrier rollovers,
container misrouting, or security restrictions:

- Validate the cause with the terminal or carrier.
- Record the expected release time and revised ETA.
- Protect refrigerated cargo with powered storage and temperature monitoring.
- Rebook the appointment, route, rail connection, or carrier as applicable.
- Escalate when the delay threatens exposure limits, customer promises, or
  downstream appointments.

#### 6.6 Traffic, weather, road, rail, or natural-disaster disruption

- Obtain a verified route and safety assessment; never dispatch into unsafe
  conditions.
- Hold at a safe approved location or use an alternate route.
- Confirm driver hours, fuel, reefer power, and cold-storage capability.
- Recalculate ETA and identify missed appointments or customer promises.
- Escalate wildfire, earthquake, flooding, storm, or road-closure impacts.

#### 6.7 Vehicle, driver, or transportation failure

For breakdowns, tire failure, fuel shortage, driver illness, fatigue,
hours-of-service limits, collision, or missed appointment:

- Protect the driver and secure the vehicle and cargo.
- Dispatch roadside assistance, a replacement driver, or rescue vehicle.
- Keep the reefer powered and monitor temperature during transfer.
- Verify chain of custody, seals, quantity, and cargo condition.
- Update ETA and arrange a new delivery or receiving appointment.
- Escalate high-risk or temperature-sensitive shipments immediately.

#### 6.8 Fulfillment-center, warehouse, or cross-dock constraint

For unavailable appointments, labor shortages, dock or staging congestion,
system outages, depot capacity limits, or power outages:

- Stop sending freight to a full or unsafe location.
- Protect priority and temperature-sensitive inventory first.
- Assign overflow doors, labor, staging, generators, or alternate capacity.
- Use a manual contingency process during system outages and reconcile it
  when systems recover.
- Confirm the destination can receive freight before dispatch.
- Replan when the Inland Empire depot or another cross-dock reaches capacity.

#### 6.9 Customs, documentation, inspection, or cargo-condition issue

For customs holds, missing documents, seal mismatch, damaged cargo, suspected
contamination, or failed inspection:

- Place the shipment on hold and preserve chain of custody.
- Notify customs, compliance, quality, carrier, and the Tier 2 manager.
- Correct documents or arrange inspection without bypassing controls.
- Record damage, seal numbers, quantities, and timestamps.
- Keep refrigerated cargo in its validated range while awaiting release.
- Obtain approved disposition before relabeling, returning, disposing, or
  delivering the shipment.

#### 6.10 High-risk or cascading delay

When `RISK_CLS_TXT = High Risk` and `DELAY_PROB_DEC > 0.65`, or when a delay
causes a missed rail connection, appointment, customer SLA, or temperature
window:

- Rank the shipment above routine congestion-only work.
- Identify every downstream appointment and dependent shipment.
- Create a recovery plan with an owner, next action, deadline, and fallback.
- Notify the customer or account owner through the approved channel.
- Review the plan at each scheduled update until the shipment is stable.

### 7. Escalation and Communication Timing

- **Immediately:** Safety or security threats, active temperature breaches,
  contamination, refrigerated power loss, or blocked emergency access.
- **Within 15 minutes:** Critical congestion, high-risk triggers, breakdowns
  with perishables, customs holds threatening exposure, or likely missed
  customer promises.
- **Within 30 minutes:** Elevated congestion, appointment failure, labor or
  system outage, equipment shortage, or material route disruption.
- **At every material change:** Communicate cause, affected shipments,
  temperature where applicable, revised ETA, owner, mitigation, and next update.

The Area Manager must hand over every open incident with severity, owner,
current state, pending decisions, deadlines, and fallback plan.

### 8. Recovery, Closure, and After-Action Review

An incident is not closed merely because freight starts moving. Confirm that:

- The hazard or trigger is controlled.
- Temperature and exposure have an approved disposition.
- Quantity, seals, condition, and chain of custody reconcile.
- Route, appointment, ETA, and receiving capacity are confirmed.
- Notifications and approvals are documented.
- The incident log contains actions, timestamps, owners, and outcomes.
- Corrective actions for equipment, systems, labor, or carriers have owners
  and due dates.

Critical incidents require an after-action review covering root cause,
detection quality, response time, product impact, customer impact, and
preventive actions. Normal routing may resume only after the responsible
operational owner confirms that the destination and controls are ready.

### 9. Severity, Ownership, and Response

- **Normal (`PRT_CNG_LVL` <= 3.0):** Continue standard routing and monitor the shipment.
- **Elevated (`3.0 < PRT_CNG_LVL <= 7.0`):** The dispatcher reviews alternate appointments and routes and records the expected ETA impact.
- **Critical (`PRT_CNG_LVL` > 7.0):** Suspend standard routing and divert active shipments to the **Inland Empire Overflow Depot (San Bernardino)** for cross-docking.

The dispatcher owns initial validation and mitigation. The Tier 2 Logistics Manager approves exceptions, prioritizes high-risk shipments, and coordinates customer or carrier escalation. Any refrigerated shipment with a temperature breach takes priority over a congestion-only incident.

### 10. Incident Response Workflow

Every incident follows this workflow:

```text
Detect anomaly
→ Validate sensor or operational data
→ Classify severity
→ Notify the responsible person
→ Execute mitigation
→ Log the incident
→ Monitor recovery
→ Close the incident
```

The incident log must include the shipment or vehicle identifier, detection timestamp, triggering field and value, current location, expected delay, person notified, mitigation taken, and resolution timestamp. Normal routing may resume only after port operations are confirmed stable and the dispatcher updates the shipment ETA.

### 11. Additional Delivery-Impact Scenarios

The following events may affect delivery time, customer service levels, or
cargo condition:

- Heavy traffic, accidents, road closures, or flooding.
- Severe weather, wildfire, earthquake, or storm.
- Driver fatigue, illness, or hours-of-service limits.
- Vehicle breakdown, tire failure, or fuel shortage.
- Warehouse receiving appointment unavailable.
- Labor strike or staffing shortage.
- Customs, documentation, or inspection hold.
- Damaged, missing, or incorrect shipping documents.
- Port, rail, chassis, or container shortage.
- Wrong address or failed delivery appointment.
- Security incident, theft, or restricted facility access.
- Depot or cross-dock capacity exceeded.

The dispatcher must update the ETA, record the operational cause, identify
affected downstream appointments, and apply the appropriate escalation path.

### 12. Operational Policy Triggers

The AI assistant and operations team should apply these triggers:

- **Temperature breach:** `IOT_TEMP_VAL_C` exceeds the applicable
  product-specific maximum temperature.
- **Extended exposure:** A temperature breach lasts longer than the
  product's allowed exposure time.
- **Port disruption:** `PRT_CNG_LVL` is greater than **7.0**.
- **High-risk delay:** `RISK_CLS_TXT` equals `High Risk` and
  `DELAY_PROB_DEC` is greater than **0.65**.
- **Cold-chain priority:** The shipment contains perishable cargo and has a
  temperature breach, or the expected delay threatens its validated
  temperature window.

If multiple triggers occur, the cold-chain or safety risk takes priority over
congestion-only or schedule-only delays.

### 13. Product-Specific Temperature Requirements

The default chilled range must not be applied blindly to every product.
Product requirements should be maintained with these fields:

```text
product_type
minimum_temperature_c
maximum_temperature_c
maximum_exposure_minutes
required_action
```

Examples include chilled seafood, frozen food, and vaccines, which may each
require different validated temperature ranges. The product-specific
requirement overrides the general `0.0°C–4.0°C` default.
