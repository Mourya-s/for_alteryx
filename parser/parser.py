import xml.etree.ElementTree as ET
import json
import sys

class AlteryxParser:

    def __init__(self, workflow_path):
        self.tree = ET.parse(workflow_path)
        self.root = self.tree.getroot()

    def extract(self):

        workflow = {
            "nodes": [],
            "connections": []
        }

        for node in self.root.findall(".//Node"):

            node_data = {
                "tool_id": node.get("ToolID")
            }

            gui = node.find("GuiSettings")

            if gui is not None:
                node_data["plugin"] = gui.get("Plugin")

            workflow["nodes"].append(node_data)

        for conn in self.root.findall(".//Connection"):

            workflow["connections"].append({
                "origin": conn.get("Origin"),
                "destination": conn.get("Destination")
            })

        return workflow


if __name__ == "__main__":

    workflow_path = sys.argv[1]

    parser = AlteryxParser(workflow_path)

    data = parser.extract()

    with open("generated/workflow.json", "w") as f:
        json.dump(data, f, indent=2)

    print("JSON created")