# OPDS-AI Repo Structure

```
opds-ai/
├── README.md                          # Main project README
├── .gitignore
├── docker-compose.yml                 # Full Phase 1 + 2 stack (5 services)
├── simulator.py                       # Data simulator — 2s interval live inserts
│
├── mcp-mysql/
│   ├── server.py                      # FastAPI tool server — 5 endpoints
│   └── Dockerfile                     # Python 3.12-slim, fastapi, uvicorn, mysql-connector
│
└── docs/
    ├── STANDARDISED_WORK_v2.0.docx    # Full installation + operations guide
    └── screenshots/
        ├── grafana-kpi.png            # Grafana 5-panel KPI dashboard
        ├── metabase-predictive.png    # Metabase predictive maintenance dashboard
        ├── openwebui-tool-response.png # LLM answering with real data + citations
        └── fastapi-tools.png          # FastAPI /docs — 5 tools listed
```
