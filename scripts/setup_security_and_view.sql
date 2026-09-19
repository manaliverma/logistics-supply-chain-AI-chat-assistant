/*
    Phase 2: least-privilege SQL Server access for the AI agent.

    Run with SQLCMD variable substitution, for example:
    sqlcmd ... -v AGENT_FDE_RO_PASSWORD="AgentPassword2026!"

    Do not replace the placeholder with a password in the tracked file.
*/

USE [master];
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'FDE_VIEWS')
    EXEC(N'CREATE SCHEMA [FDE_VIEWS] AUTHORIZATION [dbo]');
GO

IF OBJECT_ID(N'[FDE_VIEWS].[VW_ACTIVE_FLEET]', N'V') IS NOT NULL
    DROP VIEW [FDE_VIEWS].[VW_ACTIVE_FLEET];
GO

CREATE VIEW [FDE_VIEWS].[VW_ACTIVE_FLEET]
AS
SELECT
    shipment_id,
    product_type,
    product_category,
    fulfillment_center,
    destination_region,
    timestamp,
    vehicle_gps_latitude,
    vehicle_gps_longitude,
    iot_temperature,
    max_temperature_c,
    max_exposure_minutes,
    exposure_duration_minutes,
    cold_chain_required,
    reefer_power_available,
    weather_status,
    road_closure,
    port_congestion_level,
    depot_capacity_pct,
    risk_classification,
    delay_probability,
    route_risk_level
FROM [dbo].[TBL_SC_FLEET_ENRICHED];
GO

IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'USR_FDE_RO')
BEGIN
    CREATE LOGIN [USR_FDE_RO]
    WITH PASSWORD = N'$(AGENT_FDE_RO_PASSWORD)',
         CHECK_POLICY = ON,
         CHECK_EXPIRATION = OFF;
END;
GO

IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'USR_FDE_RO')
    CREATE USER [USR_FDE_RO] FOR LOGIN [USR_FDE_RO];
GO

DENY SELECT ON OBJECT::[dbo].[TBL_SC_FLEET_HIST_RAW] TO [USR_FDE_RO];
DENY SELECT ON OBJECT::[dbo].[TBL_SC_FLEET_ENRICHED] TO [USR_FDE_RO];
GRANT SELECT ON OBJECT::[FDE_VIEWS].[VW_ACTIVE_FLEET] TO [USR_FDE_RO];
GO
