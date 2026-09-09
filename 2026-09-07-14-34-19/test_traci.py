import traci

sumo_cmd = [
    "sumo-gui",
    "-c",
    "osm.sumocfg",
    "--start"
]

traci.start(sumo_cmd)

print("TraCI connected.")
print("Simulation starting...\n")

for step in range(300):

    traci.simulationStep()

    current_time = traci.simulation.getTime()

    loaded = traci.simulation.getLoadedNumber()
    arrived = traci.simulation.getArrivedNumber()
    active = len(traci.vehicle.getIDList())
    expected = traci.simulation.getMinExpectedNumber()

    if step % 10 == 0:

        print(
            f"Time: {current_time:6.1f}s | "
            f"Loaded: {loaded:4d} | "
            f"Active: {active:4d} | "
            f"Arrived: {arrived:4d} | "
            f"Expected: {expected:4d}"
        )

        if active > 0:

            vehicle_ids = traci.vehicle.getIDList()

            print("  Active vehicles:")

            for vehicle_id in vehicle_ids[:5]:

                edge = traci.vehicle.getRoadID(vehicle_id)
                speed = traci.vehicle.getSpeed(vehicle_id)

                print(
                    f"    {vehicle_id} → "
                    f"edge={edge}, "
                    f"speed={speed:.2f} m/s"
                )

            print()

traci.close()