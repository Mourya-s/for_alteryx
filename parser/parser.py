import xml.etree.ElementTree as ET
import json
import sys


class AlteryxParser:
    """
    Parses an Alteryx .yxmd/.yxwz workflow XML file into a JSON-friendly
    structure containing nodes (tools) and connections.

    Backward compatible with the original parser output:
        {
          "nodes": [{"tool_id": "...", "plugin": "..."}],
          "connections": [{"origin": "...", "destination": "..."}]
        }

    Extended output adds (without removing/altering the above):
        - "workflow_name"
        - node["tool_type"]        -> friendly/normalized tool name
        - node["configuration"]    -> tool-specific extracted settings ({}
                                       if nothing could be found / tool is
                                       unsupported)
        - "skipped_report_tools"   -> tool_id/plugin of any Reporting-category
                                       tools (Render, Layout, TextBox, Chart,
                                       Image, etc.) found in the workflow.
                                       These are intentionally left out of
                                       "nodes" and "connections" - they only
                                       build report output and aren't part of
                                       the data-prep logic needed for the
                                       Databricks (DAB/SDP) build.

    Macro tools (a Node whose EngineSettings points at a .yxmc, or whose
    Plugin/EngineDll contains "Macro") are resolved to tool_type "Macro" and
    get a "configuration" containing the macro's file path plus a best-effort
    dump of whatever question/answer values are stored in that node's
    <Configuration> block. Macro internals themselves are not parsed - Alteryx
    macros are just referenced, not expanded, since analyzing what's inside a
    macro would need that macro's own .yxmc file, not the calling workflow.
    """

    # Maps the last dot-delimited segment of a GuiSettings "Plugin"
    # attribute to a normalized tool_type name and the handler used to
    # pull its configuration. Add new entries here to support more tools
    # without touching any other logic.
    PLUGIN_TOOL_MAP = {
        "DbFileInput": "InputData",
        "TextInput": "InputData",
        "DbFileOutput": "OutputData",
        "Filter": "Filter",
        "Formula": "Formula",
        "AlteryxSelect": "Select",
        "Join": "Join",
        "Summarize": "Summarize",
        "Union": "Union",
        "Sort": "Sort",
        "Unique": "Unique",
        "Directory": "Directory",
    }

    # Last dot-delimited plugin segments belonging to Alteryx's "Reporting"
    # tool category. Any node whose plugin matches one of these (or whose
    # plugin string contains "report", case-insensitive) is a report/layout
    # tool and gets skipped entirely - it only feeds a rendered report output,
    # not the data pipeline that matters for the Databricks build.
    REPORT_TOOL_NAMES = {
        "RenderTool", "Layout", "TextBox", "Reporting_Table", "ReportingTable",
        "ChartTool", "ImageTool", "ReportMap", "ReportHeader", "ReportFooter",
        "DocumentBuilder", "PptTool", "CondReport", "ReportText",
    }

    def __init__(self, workflow_path):
        self.tree = ET.parse(workflow_path)
        self.root = self.tree.getroot()

    # ------------------------------------------------------------------ #
    # Main extraction
    # ------------------------------------------------------------------ #

    def extract(self):

        workflow = {
            "workflow_name": self._extract_workflow_name(),
            "nodes": [],
            "connections": [],
            "skipped_report_tools": []
        }

        # Tool IDs that made it into "nodes" - used below to drop any
        # connection that touches a skipped report tool.
        kept_tool_ids = set()

        for node in self.root.findall(".//Node"):

            tool_id = node.get("ToolID")

            gui = node.find("GuiSettings")
            plugin = gui.get("Plugin") if gui is not None else None

            if self._is_report_tool(plugin):
                workflow["skipped_report_tools"].append({
                    "tool_id": tool_id,
                    "plugin": plugin
                })
                continue

            node_data = {"tool_id": tool_id}
            if plugin is not None:
                node_data["plugin"] = plugin

            if self._is_macro_tool(node, plugin):
                tool_type = "Macro"
            else:
                tool_type = self._resolve_tool_type(plugin)

            node_data["tool_type"] = tool_type

            node_data["configuration"] = self._extract_configuration(
                node, tool_type
            )

            workflow["nodes"].append(node_data)
            kept_tool_ids.add(tool_id)

        for conn in self.root.findall(".//Connection"):

            origin_id = conn.get("Origin")
            destination_id = conn.get("Destination")

            # Drop connections in/out of a skipped report tool so the
            # output never references a node that isn't there.
            if origin_id not in kept_tool_ids or destination_id not in kept_tool_ids:
                continue

            workflow["connections"].append({
                "origin": origin_id,
                "destination": destination_id
            })

        return workflow

    # ------------------------------------------------------------------ #
    # Helpers - workflow / tool type resolution
    # ------------------------------------------------------------------ #

    def _extract_workflow_name(self):
        try:
            props = self.root.find("./Properties/MetaInfo/Name")
            if props is not None and props.text:
                return props.text.strip()
        except Exception:
            pass
        return ""

    def _is_report_tool(self, plugin):
        """
        True if this plugin belongs to Alteryx's Reporting tool category
        (Render, Layout, TextBox, Chart, Image, etc.) - these are skipped
        entirely since they only produce a rendered report, not data the
        Databricks pipeline needs.
        """
        if not plugin:
            return False

        if "report" in plugin.lower():
            return True

        last_segment = plugin.split(".")[-1]
        return last_segment in self.REPORT_TOOL_NAMES

    def _is_macro_tool(self, node, plugin):
        """
        True if this Node invokes a macro (standard, batch, or iterative).
        Alteryx records this via an <EngineSettings> element whose EngineDll
        points at the macro engine and/or carries a Macro="...\\something.yxmc"
        attribute; some macros also surface "Macro" directly in the plugin
        string.
        """
        engine = node.find("./Properties/EngineSettings")
        if engine is not None:
            engine_dll = (engine.get("EngineDll") or "").lower()
            if "macro" in engine_dll or engine.get("Macro"):
                return True

        if plugin and "macro" in plugin.lower():
            return True

        return False

    def _resolve_tool_type(self, plugin):
        if not plugin:
            return "Unknown"

        last_segment = plugin.split(".")[-1]

        if last_segment in self.PLUGIN_TOOL_MAP:
            return self.PLUGIN_TOOL_MAP[last_segment]

        # Safely ignore unsupported tools - still record something useful
        # instead of failing.
        return last_segment or "Unknown"

    def _extract_configuration(self, node, tool_type):
        """
        Dispatches to the correct tool-specific extractor. Always returns
        a dict - an empty one if configuration cannot be found or the
        tool type is unsupported, so unsupported tools never break
        parsing.
        """

        handlers = {
            "InputData": self._extract_input_data_config,
            "OutputData": self._extract_output_data_config,
            "Filter": self._extract_filter_config,
            "Formula": self._extract_formula_config,
            "Select": self._extract_select_config,
            "Join": self._extract_join_config,
            "Summarize": self._extract_summarize_config,
            "Union": self._extract_union_config,
            "Sort": self._extract_sort_config,
            "Unique": self._extract_unique_config,
            "Directory": self._extract_directory_config,
            "Macro": self._extract_macro_config,
        }

        handler = handlers.get(tool_type)
        if handler is None:
            return {}

        try:
            config = handler(node)
            return config if config is not None else {}
        except Exception:
            # Never let a single tool's malformed/unexpected XML break
            # the rest of the parse.
            return {}

    # ------------------------------------------------------------------ #
    # Small shared XML utilities
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_config_root(node):
        """Returns the <Configuration> element for a node, or None."""
        return node.find("./Properties/Configuration")

    @staticmethod
    def _text(elem):
        if elem is not None and elem.text:
            return elem.text.strip()
        return None

    @staticmethod
    def _connection_endpoint(conn, side):
        """
        Reads a Connection element's Origin/Destination info, tolerant of
        both the standard Alteryx shape (nested <Origin ToolID="" Connection=""/>
        child elements) and a flat-attribute shape (Origin/Destination as
        direct attributes on <Connection>, as used by the base extraction
        loop in this parser). Returns (tool_id, connection_name).
        connection_name is None when it cannot be determined (flat shape).
        """
        child = conn.find(side)
        if child is not None:
            return child.get("ToolID"), child.get("Connection")
        return conn.get(side), None

    # ------------------------------------------------------------------ #
    # Tool-specific extractors
    # ------------------------------------------------------------------ #

    def _extract_input_data_config(self, node):
        config = {}
        cfg_root = self._get_config_root(node)
        if cfg_root is None:
            return config

        file_elem = cfg_root.find(".//File")
        if file_elem is not None:
            raw = self._text(file_elem)
            connection_string = raw

            path = raw
            table = None

            # Common Alteryx pattern for DB/Excel sources:
            # "path|||`TableName`" or "path|Table"
            if raw and "|" in raw:
                parts = [p for p in raw.split("|") if p]
                path = parts[0]
                if len(parts) > 1:
                    table = parts[-1].strip("`")

            if path:
                config["path"] = path
            if connection_string:
                config["connection_string"] = connection_string
            if table:
                config["table"] = table

            file_format = file_elem.get("FileFormat")
            if file_format is not None:
                config["format"] = file_format

        # Some inputs use a dedicated <Table> or <TableName> element
        table_elem = cfg_root.find(".//Table")
        if table_elem is not None:
            table_text = self._text(table_elem)
            if table_text:
                config["table"] = table_text

        return config

    def _extract_output_data_config(self, node):
        config = {}
        cfg_root = self._get_config_root(node)
        if cfg_root is None:
            return config

        file_elem = cfg_root.find(".//File")
        if file_elem is not None:
            raw = self._text(file_elem)
            if raw:
                path = raw.split("|")[0] if "|" in raw else raw
                config["path"] = path
                config["connection_string"] = raw

            file_format = file_elem.get("FileFormat")
            if file_format is not None:
                config["format"] = file_format

        write_mode_elem = cfg_root.find(".//WriteMode")
        if write_mode_elem is not None:
            write_mode = self._text(write_mode_elem)
            if write_mode:
                config["write_mode"] = write_mode

        # Overwrite/append behaviour is sometimes encoded on the File tag
        # itself for some connectors (e.g. Output Options attribute).
        if file_elem is not None:
            output_option = file_elem.get("Output Option") or file_elem.get(
                "OutputOption"
            )
            if output_option:
                config["write_mode"] = output_option

        return config

    def _extract_filter_config(self, node):
        config = {}
        cfg_root = self._get_config_root(node)
        if cfg_root is None:
            return config

        expression_elem = cfg_root.find(".//Expression")
        expression = self._text(expression_elem)
        if expression:
            config["expression"] = expression

        mode_elem = cfg_root.find(".//Mode")
        mode = self._text(mode_elem)
        if mode:
            config["mode"] = mode

        # True/False branch information is derived from the workflow's
        # connections where this node is the origin.
        tool_id = node.get("ToolID")
        outputs = []
        for conn in self.root.findall(".//Connection"):
            origin_id, origin_name = self._connection_endpoint(conn, "Origin")
            if origin_id == tool_id:
                dest_id, _ = self._connection_endpoint(conn, "Destination")
                outputs.append({
                    "connection": origin_name,
                    "destination_tool_id": dest_id
                })
        if outputs:
            config["outputs"] = outputs

        return config

    def _extract_formula_config(self, node):
        config = {}
        cfg_root = self._get_config_root(node)
        if cfg_root is None:
            return config

        formulas = []
        for field in cfg_root.findall(".//FormulaFields/FormulaField"):
            formulas.append({
                "field": field.get("field"),
                "expression": field.get("expression"),
                "data_type": field.get("type"),
            })

        if formulas:
            config["formulas"] = formulas
            # Convenience top-level fields for the (common) single-formula
            # case, without discarding the full list above.
            config["target_field"] = formulas[0].get("field")
            config["expression"] = formulas[0].get("expression")
            config["data_type"] = formulas[0].get("data_type")

        return config

    def _extract_select_config(self, node):
        config = {}
        cfg_root = self._get_config_root(node)
        if cfg_root is None:
            return config

        fields = []
        for field in cfg_root.findall(".//SelectFields/SelectField"):
            fields.append({
                "field": field.get("field"),
                "selected": field.get("selected"),
                "rename": field.get("rename"),
                "type": field.get("type"),
            })

        if fields:
            config["fields"] = fields
            config["selected_fields"] = [
                f["field"] for f in fields
                if f.get("selected") in ("True", None) and f.get("field")
            ]
            config["renamed_fields"] = [
                {"field": f["field"], "rename": f["rename"]}
                for f in fields if f.get("rename")
            ]
            config["field_types"] = {
                f["field"]: f["type"] for f in fields
                if f.get("field") and f.get("type")
            }

        return config

    def _extract_join_config(self, node):
        config = {}
        cfg_root = self._get_config_root(node)
        if cfg_root is None:
            return config

        left_keys = []
        right_keys = []

        for join_info in cfg_root.findall(".//JoinInfo"):
            connection = join_info.get("connection")
            fields = [
                f.get("field")
                for f in join_info.findall("./Field")
                if f.get("field")
            ]
            if connection == "Left":
                left_keys.extend(fields)
            elif connection == "Right":
                right_keys.extend(fields)

        if left_keys:
            config["left_keys"] = left_keys
        if right_keys:
            config["right_keys"] = right_keys

        join_type_elem = cfg_root.find(".//JoinType")
        join_type = self._text(join_type_elem)
        config["join_type"] = join_type if join_type else "Inner"

        # Unmatched (Left/Right) outputs are exposed as distinct output
        # connections off this tool.
        tool_id = node.get("ToolID")
        unmatched_outputs = []
        for conn in self.root.findall(".//Connection"):
            origin_id, conn_name = self._connection_endpoint(conn, "Origin")
            if origin_id == tool_id and conn_name in ("Left", "Right"):
                unmatched_outputs.append(conn_name)
        if unmatched_outputs:
            config["unmatched_outputs"] = sorted(set(unmatched_outputs))

        return config

    def _extract_summarize_config(self, node):
        config = {}
        cfg_root = self._get_config_root(node)
        if cfg_root is None:
            return config

        group_by_fields = []
        aggregates = []

        for field in cfg_root.findall(".//SummarizeFields/SummarizeField"):
            action = field.get("action")
            entry = {
                "field": field.get("field"),
                "action": action,
                "rename": field.get("rename"),
            }
            if action and action.lower() == "groupby":
                group_by_fields.append(field.get("field"))
            else:
                aggregates.append(entry)

        if group_by_fields:
            config["group_by_fields"] = group_by_fields
        if aggregates:
            config["aggregate_columns"] = aggregates
            config["aggregation_functions"] = sorted(set(
                a["action"] for a in aggregates if a.get("action")
            ))

        return config

    def _extract_union_config(self, node):
        config = {}
        cfg_root = self._get_config_root(node)
        if cfg_root is None:
            return config

        mode_elem = cfg_root.find(".//Mode")
        mode = self._text(mode_elem)
        if mode:
            config["union_mode"] = mode

        input_mappings = []
        for source in cfg_root.findall(".//SourceFields/Source"):
            input_mappings.append({
                "name": source.get("name"),
                "fields": [
                    f.get("field") for f in source.findall("./Field")
                    if f.get("field")
                ],
            })
        if input_mappings:
            config["input_mappings"] = input_mappings

        return config

    def _extract_sort_config(self, node):
        config = {}
        cfg_root = self._get_config_root(node)
        if cfg_root is None:
            return config

        sort_fields = []
        for field in cfg_root.findall(".//SortInfo/Field"):
            sort_fields.append({
                "field": field.get("field"),
                "order": field.get("order"),
            })

        if sort_fields:
            config["sort_columns"] = sort_fields

        return config

    def _extract_unique_config(self, node):
        config = {}
        cfg_root = self._get_config_root(node)
        if cfg_root is None:
            return config

        unique_fields = []
        for field in cfg_root.findall(".//UniqueFields/Field"):
            if field.get("field") and field.get("selected", "True") == "True":
                unique_fields.append(field.get("field"))

        if unique_fields:
            config["unique_fields"] = unique_fields

        # Duplicate/unmatched output is exposed as a distinct connection
        # off this tool (commonly named "Unique" / "Duplicate").
        tool_id = node.get("ToolID")
        outputs = set()
        for conn in self.root.findall(".//Connection"):
            origin_id, conn_name = self._connection_endpoint(conn, "Origin")
            if origin_id == tool_id and conn_name:
                outputs.add(conn_name)
        if outputs:
            config["outputs"] = sorted(outputs)

        return config

    def _extract_macro_config(self, node):
        config = {}

        engine = node.find("./Properties/EngineSettings")
        if engine is not None:
            macro_path = engine.get("Macro")
            if macro_path:
                config["macro_path"] = macro_path

            engine_dll = engine.get("EngineDll")
            if engine_dll:
                config["engine_dll"] = engine_dll

            entry_point = engine.get("EngineDllEntryPoint")
            if entry_point:
                config["engine_entry_point"] = entry_point

        cfg_root = self._get_config_root(node)
        if cfg_root is not None:
            macro_inputs = self._extract_macro_inputs(cfg_root)
            if macro_inputs:
                config["macro_inputs"] = macro_inputs

        return config

    @staticmethod
    def _extract_macro_inputs(cfg_root):
        """
        Best-effort extraction of a macro's exposed question/answer values.
        A macro's configuration schema is defined by whoever built the
        macro, so there's no fixed structure to target the way there is for
        a built-in tool like Filter or Formula. This walks every element
        under <Configuration> and records:
          - elements with a name/Name attribute (the common
            "<Value name='Question1'>42</Value>" pattern used by the
            Interface Designer's Action tool), keyed by that name
          - otherwise, any plain leaf element's text, keyed by its tag

        Returns {} if nothing recognizable is found - the raw macro_path
        captured above is still preserved either way.
        """
        inputs = {}

        for elem in cfg_root.iter():
            if elem is cfg_root:
                continue

            name_attr = elem.get("name") or elem.get("Name")
            if name_attr:
                if elem.text and elem.text.strip():
                    inputs[name_attr] = elem.text.strip()
                elif elem.get("value") is not None:
                    inputs[name_attr] = elem.get("value")
                continue

            if len(elem) == 0 and elem.text and elem.text.strip():
                inputs.setdefault(elem.tag, elem.text.strip())

        return inputs

    def _extract_directory_config(self, node):
        config = {}
        cfg_root = self._get_config_root(node)
        if cfg_root is None:
            return config

        dir_elem = cfg_root.find(".//Directory")
        directory_path = self._text(dir_elem)
        if directory_path:
            config["directory_path"] = directory_path

        file_specs = []
        for spec in cfg_root.findall(".//FileSpecs"):
            spec_text = self._text(spec)
            if spec_text:
                file_specs.append(spec_text)
        if file_specs:
            config["file_specifications"] = file_specs

        recurse_elem = cfg_root.find(".//SearchSubDirs")
        recurse_text = self._text(recurse_elem)
        if recurse_text is None and dir_elem is not None:
            recurse_text = dir_elem.get("SearchSubDirs")
        if recurse_text is not None:
            config["recursive"] = recurse_text

        return config


if __name__ == "__main__":

    workflow_path = sys.argv[1]

    parser = AlteryxParser(workflow_path)

    data = parser.extract()

    with open("generated/workflow.json", "w") as f:
        json.dump(data, f, indent=2)

    print("JSON created")