from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.responses import HTMLResponse


def install_local_docs(app: FastAPI) -> None:
    @app.get("/docs", include_in_schema=False)
    async def local_docs() -> HTMLResponse:
        return HTMLResponse(_docs_html(app))

    @app.get("/redoc", include_in_schema=False)
    async def local_redoc() -> HTMLResponse:
        return HTMLResponse(_docs_html(app))


def _docs_html(app: FastAPI) -> str:
    title = json.dumps(app.title)
    version = json.dumps(app.version)
    description = json.dumps(app.description or "")
    openapi_url = json.dumps(app.openapi_url or "/openapi.json")

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{app.title} - API Docs</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f8fb;
      --panel: #ffffff;
      --text: #17202a;
      --muted: #607083;
      --line: #dbe3ed;
      --get: #087f5b;
      --post: #1d4ed8;
      --put: #9a5b00;
      --patch: #7c3aed;
      --delete: #b42318;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }}
    header {{
      background: #10241c;
      color: #f8fff9;
      padding: 28px clamp(18px, 4vw, 56px);
      border-bottom: 4px solid #46b36f;
    }}
    header h1 {{ margin: 0; font-size: clamp(1.5rem, 3vw, 2.25rem); letter-spacing: 0; }}
    header p {{ margin: 8px 0 0; max-width: 900px; color: #d8eadc; }}
    main {{ width: min(1180px, calc(100% - 32px)); margin: 22px auto 48px; }}
    .toolbar {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: center;
      margin-bottom: 18px;
    }}
    input {{
      width: 100%;
      min-height: 42px;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 0 14px;
      font: inherit;
      background: var(--panel);
    }}
    .meta {{ color: var(--muted); font-size: 0.95rem; white-space: nowrap; }}
    .tag {{ margin: 24px 0 12px; font-size: 1.15rem; }}
    article {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      margin: 10px 0;
      overflow: hidden;
      box-shadow: 0 1px 2px rgba(16, 36, 28, 0.05);
    }}
    details > summary {{
      display: grid;
      grid-template-columns: 78px minmax(0, 1fr);
      gap: 12px;
      align-items: center;
      padding: 14px 16px;
      cursor: pointer;
      list-style: none;
    }}
    details > summary::-webkit-details-marker {{ display: none; }}
    .method {{
      border-radius: 6px;
      color: #fff;
      font-weight: 750;
      font-size: 0.78rem;
      text-align: center;
      padding: 5px 8px;
    }}
    .GET {{ background: var(--get); }}
    .POST {{ background: var(--post); }}
    .PUT {{ background: var(--put); }}
    .PATCH {{ background: var(--patch); }}
    .DELETE {{ background: var(--delete); }}
    .path {{ font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace; overflow-wrap: anywhere; }}
    .content {{ border-top: 1px solid var(--line); padding: 14px 16px 18px; }}
    .summary {{ margin: 0 0 8px; font-weight: 650; }}
    .description {{ margin: 0 0 16px; color: var(--muted); white-space: pre-wrap; }}
    h3 {{ margin: 16px 0 8px; font-size: 0.95rem; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.92rem; }}
    th, td {{ border-top: 1px solid var(--line); padding: 8px; text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 650; }}
    code, pre {{ font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace; }}
    pre {{
      margin: 8px 0 0;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f9fbfd;
      overflow: auto;
      font-size: 0.9rem;
    }}
    .empty {{ color: var(--muted); font-size: 0.92rem; }}
    .error {{
      background: #fff4f2;
      border: 1px solid #ffcdc7;
      color: #8a1f13;
      border-radius: 8px;
      padding: 14px;
    }}
    @media (max-width: 700px) {{
      .toolbar {{ grid-template-columns: 1fr; }}
      .meta {{ white-space: normal; }}
      details > summary {{ grid-template-columns: 64px minmax(0, 1fr); padding: 12px; }}
      .content {{ padding: 12px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1 id="title"></h1>
    <p id="description"></p>
  </header>
  <main>
    <div class="toolbar">
      <input id="filter" type="search" placeholder="Filter endpoints by path, method, tag, or summary" autocomplete="off">
      <div class="meta" id="meta"></div>
    </div>
    <section id="docs">Loading API schema...</section>
  </main>
  <script>
    const appTitle = {title};
    const appVersion = {version};
    const appDescription = {description};
    const openapiUrl = {openapi_url};
    const methods = ["get", "post", "put", "patch", "delete", "options", "head"];
    let operations = [];

    document.getElementById("title").textContent = `${{appTitle}} ${{appVersion ? "v" + appVersion : ""}}`;
    document.getElementById("description").textContent = appDescription || "OpenAPI endpoint reference";

    function escapeHtml(value) {{
      return String(value ?? "").replace(/[&<>"']/g, char => ({{
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }}[char]));
    }}

    function schemaName(ref) {{
      return ref ? ref.split("/").pop() : "";
    }}

    function describeSchema(schema) {{
      if (!schema || Object.keys(schema).length === 0) return "JSON response schema not declared";
      if (schema.$ref) return schemaName(schema.$ref);
      if (schema.anyOf) return schema.anyOf.map(describeSchema).join(" | ");
      if (schema.oneOf) return schema.oneOf.map(describeSchema).join(" | ");
      if (schema.allOf) return schema.allOf.map(describeSchema).join(" + ");
      if (schema.type === "array") return `array of ${{describeSchema(schema.items)}}`;
      if (schema.type === "object" && schema.properties) return schema.title || "object";
      if (schema.additionalProperties) return "object";
      return schema.format ? `${{schema.type || "value"}}(${{schema.format}})` : (schema.type || schema.title || "value");
    }}

    function schemaBlock(schema) {{
      if (!schema || Object.keys(schema).length === 0) return '<div class="empty">JSON response schema not declared.</div>';
      if (schema.$ref) return `<code>${{escapeHtml(schemaName(schema.$ref))}}</code>`;
      if (schema.properties) {{
        const rows = Object.entries(schema.properties).map(([name, prop]) => `
          <tr><td><code>${{escapeHtml(name)}}</code></td><td>${{escapeHtml(describeSchema(prop))}}</td><td>${{escapeHtml(prop.description || "")}}</td></tr>
        `).join("");
        return `<table><thead><tr><th>Field</th><th>Type</th><th>Description</th></tr></thead><tbody>${{rows}}</tbody></table>`;
      }}
      return `<pre>${{escapeHtml(JSON.stringify(schema, null, 2))}}</pre>`;
    }}

    function parametersTable(parameters) {{
      if (!parameters || parameters.length === 0) return '<div class="empty">No parameters.</div>';
      const rows = parameters.map(param => `
        <tr>
          <td><code>${{escapeHtml(param.name)}}</code></td>
          <td>${{escapeHtml(param.in)}}</td>
          <td>${{param.required ? "yes" : "no"}}</td>
          <td>${{escapeHtml(describeSchema(param.schema))}}</td>
          <td>${{escapeHtml(param.description || param.schema?.description || "")}}</td>
        </tr>
      `).join("");
      return `<table><thead><tr><th>Name</th><th>In</th><th>Required</th><th>Type</th><th>Description</th></tr></thead><tbody>${{rows}}</tbody></table>`;
    }}

    function requestBodyBlock(requestBody) {{
      if (!requestBody) return '<div class="empty">No request body.</div>';
      return Object.entries(requestBody.content || {{}}).map(([contentType, media]) => `
        <p><code>${{escapeHtml(contentType)}}</code></p>${{schemaBlock(media.schema)}}
      `).join("") || '<div class="empty">No request body content declared.</div>';
    }}

    function responsesBlock(responses) {{
      const rows = Object.entries(responses || {{}}).map(([status, response]) => {{
        const content = response.content || {{}};
        const schemas = Object.entries(content).map(([contentType, media]) =>
          `${{escapeHtml(contentType)}}: ${{escapeHtml(describeSchema(media.schema))}}`
        ).join("<br>");
        return `<tr><td><code>${{escapeHtml(status)}}</code></td><td>${{escapeHtml(response.description || "")}}</td><td>${{schemas || '<span class="empty">No schema</span>'}}</td></tr>`;
      }}).join("");
      return rows ? `<table><thead><tr><th>Status</th><th>Description</th><th>Schema</th></tr></thead><tbody>${{rows}}</tbody></table>` : '<div class="empty">No responses declared.</div>';
    }}

    function collectOperations(spec) {{
      const collected = [];
      Object.entries(spec.paths || {{}}).forEach(([path, pathItem]) => {{
        methods.forEach(method => {{
          const operation = pathItem[method];
          if (!operation) return;
          collected.push({{
            path,
            method: method.toUpperCase(),
            tag: (operation.tags && operation.tags[0]) || "Default",
            operation
          }});
        }});
      }});
      return collected;
    }}

    function render() {{
      const query = document.getElementById("filter").value.trim().toLowerCase();
      const docs = document.getElementById("docs");
      const filtered = operations.filter(item => {{
        const op = item.operation;
        const haystack = [item.path, item.method, item.tag, op.summary, op.description].join(" ").toLowerCase();
        return !query || haystack.includes(query);
      }});
      document.getElementById("meta").textContent = `${{filtered.length}} of ${{operations.length}} operations`;
      const grouped = filtered.reduce((acc, item) => {{
        (acc[item.tag] ||= []).push(item);
        return acc;
      }}, {{}});
      docs.innerHTML = Object.entries(grouped).map(([tag, items]) => `
        <h2 class="tag">${{escapeHtml(tag)}}</h2>
        ${{items.map(item => {{
          const op = item.operation;
          return `<article data-path="${{escapeHtml(item.path)}}">
            <details>
              <summary>
                <span class="method ${{item.method}}">${{item.method}}</span>
                <span class="path">${{escapeHtml(item.path)}}</span>
              </summary>
              <div class="content">
                <p class="summary">${{escapeHtml(op.summary || "Endpoint")}}</p>
                ${{op.description ? `<p class="description">${{escapeHtml(op.description)}}</p>` : ""}}
                <h3>Parameters</h3>${{parametersTable(op.parameters)}}
                <h3>Request Body</h3>${{requestBodyBlock(op.requestBody)}}
                <h3>Responses</h3>${{responsesBlock(op.responses)}}
              </div>
            </details>
          </article>`;
        }}).join("")}}
      `).join("") || '<div class="empty">No endpoints match the current filter.</div>';
    }}

    fetch(openapiUrl, {{ headers: {{ "accept": "application/json" }} }})
      .then(response => {{
        if (!response.ok) throw new Error(`HTTP ${{response.status}} while loading ${{openapiUrl}}`);
        return response.json();
      }})
      .then(spec => {{
        operations = collectOperations(spec);
        render();
        document.getElementById("filter").addEventListener("input", render);
      }})
      .catch(error => {{
        document.getElementById("docs").innerHTML = `<div class="error">Could not load OpenAPI schema: ${{escapeHtml(error.message)}}</div>`;
      }});
  </script>
</body>
</html>"""
