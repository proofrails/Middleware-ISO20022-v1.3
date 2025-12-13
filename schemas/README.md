# ISO 20022 XSDs (pain.001.001.09)

Place the official ISO 20022 schema files here to enable XML schema validation.

What you need
- pain.001.001.09.xsd (Customer Credit Transfer Initiation)
- Any XSDs it imports/includes (the official distribution often references common type libraries; vendor them alongside and keep relative import paths intact)

Recommended sources
- ISO 20022 Catalogue of Messages (official): requires agreeing to license/terms to download
- IFX/industry mirrors that redistribute ISO message XSDs for integration/testing purposes
- Your bank/PSP or standards provider may supply a vetted XSD bundle

Why vendor locally
- Avoid network dependency during runtime
- Ensure consistent validation across environments
- Lock schema version to pain.001.001.09 for this PoC

Expected layout
schemas/
├─ pain.001.001.09.xsd
├─ (any additional .xsd files referenced by the above)

How the app uses it
- app/iso.py will attempt to load schemas/pain.001.001.09.xsd at startup
- If present and loadable, xmlschema will validate each generated pain.001 document
- If missing, generation still works but validation is skipped (PoC mode)

Quick validation check
1) Drop the XSD(s) into this folder
2) Run the API locally
   uvicorn app.main:app --reload --port 8000
3) POST a sample record-tip (see README)
4) Inspect the server logs; if the XML fails validation, the background job will raise a detailed error message

Programmatic test
You can test the XSD compilation quickly in a Python shell:

  import xmlschema
  schema = xmlschema.XMLSchema("schemas/pain.001.001.09.xsd")
  print("Loaded:", schema.version)

Notes
- This repository does not include ISO XSDs due to licensing. Ensure you comply with the license terms of your source.
- Some distributions use absolute schemaLocation URLs. If needed, normalize schemaLocation attributes or ensure all referenced XSDs are vendored with correct relative paths.
