# Frontend → Backend Requirements

This document captures the backend dependencies that are still required for the current frontend experience to be complete.

## 1. Notifications API

### Requirement
Endpoint / data needed for notification records and unread state.

### Why frontend needs it
The application shell and role dashboards are prepared for notification-aware experiences, but the contract does not provide any backend endpoint for list/read/update operations.

### Suggested contract
Method: GET /notifications
Response: list of notification objects with at minimum `id`, `title`, `message`, `read`, `created_at`, and `link` or `resource_id`.

### Frontend blocked by
A dedicated notifications panel or inbox cannot be populated without live backend data.

## 2. Audit Log API

### Requirement
Endpoint / data needed for system audit history.

### Why frontend needs it
Super Admin screens need a traceable action timeline for instruments, applications, inspections, and certificate events.

### Suggested contract
Method: GET /audit-logs
Response: entries with `actor_name`, `action`, `resource_type`, `resource_id`, `details`, and `timestamp`.

### Frontend blocked by
The UI shell can be prepared, but the actual audit details cannot be displayed without this API.

## 3. User Management API

### Requirement
 CRUD operations for user records and role assignment.

### Why frontend needs it
Role-based administration screens need user listing, activation, deactivation, and profile editing, but no such endpoint exists in the contract.

### Suggested contract
Method: GET /users, POST /users, PATCH /users/{id}, PATCH /users/{id}/deactivate
Response: user objects with `id`, `name`, `email`, `role`, `org_name`, `status`.

### Frontend blocked by
No real user management module should be rendered as functional CRUD until the API exists.

## 4. GATC Management API

### Requirement
Administration endpoints for GATC profile and assignment records.

### Why frontend needs it
A Super Admin view for GATC onboarding and governance would fit the product information architecture, but the current contract does not expose those resources.

### Suggested contract
Method: GET /gatcs, POST /gatcs, PATCH /gatcs/{id}
Response: identifiers, name, designation, active status, and assigned region.

### Frontend blocked by
A real GATC management UI cannot be implemented without the backend contract.

## 5. LMO Management API

### Requirement
Administration endpoints for LMO roster data and field assignment metadata.

### Why frontend needs it
The admin information architecture expects officer administration, but the backend currently exposes only verification workflow endpoints.

### Suggested contract
Method: GET /lmos, POST /lmos, PATCH /lmos/{id}
Response: identifiers, name, role, district, and active status.

### Frontend blocked by
No functional LMO management CRUD should be created until the API is available.

## 6. Application Claim / Scheduling Flow

### Requirement
Already supported by the API contract: POST /applications/{id}/claim

### Why frontend needs it
This is the real lifecycle transition for `submitted → scheduled` and powers the GATC/LMO claim and assignment UX.

### Suggested contract
Method: POST /applications/{id}/claim
Body: none
Response: updated application object with `assigned_officer_id` and status changed to `scheduled`.

### Frontend blocked by
Nothing additional is blocked here; the claim flow is already implemented against the existing contract.

## 7. Scheduling Calendar

### Requirement
No standalone schedule or calendar endpoint exists.

### Why frontend needs it
The frontend must not invent a scheduling system unrelated to the actual API contract.

### Suggested contract
No additional contract is required. The scheduling experience should remain the claim workflow.

### Frontend blocked by
A fake scheduling UI or calendar screen would be misleading and is intentionally not implemented.
