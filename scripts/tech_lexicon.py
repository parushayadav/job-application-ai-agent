"""Common data/software technologies that are NOT in the skills inventory.

score_jobs.py scans every JD for these (and for every inventory skill) in code, so a posting's
gaps are found the same way every run -- the model's own keyword list varied run to run (one
NBCUniversal posting scored 34% and then 100% because the model simply left the AWS tools out).

Only add unambiguous names: whole-word matching is used, and very short or all-caps terms are
matched case-sensitively, but a term that is also an ordinary English word will still misfire.
Anything the candidate genuinely has belongs in resume/skills_inventory.md instead -- inventory
terms always win over this list.
"""

TECH_TERMS = [
    # warehouses / query engines / storage formats
    "Snowflake", "Amazon Redshift", "Redshift", "Athena", "Teradata", "Netezza", "Vertica",
    "SingleStore", "ClickHouse", "Apache Druid", "Apache Pinot", "Presto", "Trino", "Apache Hive",
    "Hive", "Impala", "Apache Iceberg", "Iceberg", "Apache Hudi", "Hudi", "Parquet", "Avro",
    "Synapse Spark",
    # AWS
    "EMR", "Kinesis", "DynamoDB", "Step Functions", "SNS", "SQS", "CloudFormation", "AWS CDK",
    "EKS", "ECS", "Fargate", "Lake Formation", "Amazon MWAA", "MWAA", "SageMaker", "Bedrock",
    "IAM", "CloudWatch", "Aurora", "RDS",
    # GCP / Azure extras
    "Dataflow", "Dataproc", "Pub/Sub", "Cloud Composer", "Vertex AI", "Cloud Functions",
    "Azure Functions", "Azure Logic Apps", "Logic Apps", "Azure Stream Analytics", "Cosmos DB",
    "Azure Cosmos DB", "Azure Key Vault", "Key Vault", "Azure Machine Learning", "Azure ML",
    "Azure OpenAI", "Microsoft Purview", "Purview", "AKS",
    # processing / streaming / orchestration / ingestion
    "Apache Flink", "Flink", "Apache Beam", "Kafka Streams", "Confluent", "RabbitMQ", "Pulsar",
    "Apache NiFi", "NiFi", "dbt", "Fivetran", "Airbyte", "Dagster", "Prefect", "Luigi", "Talend",
    "Matillion", "Debezium", "GoldenGate", "Change Data Capture", "Dask", "Polars", "Ray",
    "HBase", "Oozie", "MapReduce", "Kudu",
    # databases
    "MongoDB", "Cassandra", "Redis", "Elasticsearch", "OpenSearch", "Neo4j", "DB2", "SQLite",
    "pgvector", "Pinecone", "Weaviate", "Milvus", "Chroma",
    # languages / frameworks
    "Java", "Scala", "Golang", "Rust", "C++", "C#", ".NET", "JavaScript", "TypeScript",
    "Node.js", "React", "Angular", "Vue", "Spring Boot", "Django", "Flask", "Kotlin",
    "Ruby", "PHP", "SAS", "MATLAB", "GraphQL", "gRPC", "PowerShell", "VBA",
    # infra / devops / observability
    "Kubernetes", "Helm", "Ansible", "Puppet", "Pulumi", "GitLab CI", "GitLab", "CircleCI",
    "Argo CD", "ArgoCD", "Airflow on Kubernetes", "Prometheus", "Grafana", "Datadog", "New Relic",
    "PagerDuty", "OpenTelemetry", "Microservices", "Serverless",
    # BI / governance / quality
    "Looker", "Qlik", "MicroStrategy", "SSRS", "SSAS", "Power Automate", "Collibra", "Alation",
    "Great Expectations", "OpenLineage", "Data Contracts", "Jira", "Confluence",
    # ML / GenAI
    "PyTorch", "TensorFlow", "Keras", "Hugging Face", "LangChain", "LlamaIndex", "RAG",
    "Kubeflow", "XGBoost", "Spark MLlib", "MLlib",
    # enterprise apps
    "Salesforce", "SAP", "Workday", "ServiceNow",
]
