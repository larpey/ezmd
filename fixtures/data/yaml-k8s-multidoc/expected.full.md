---
title: "input.yaml"
source: "input.yaml"
source_type: data
converter: data.yaml
converter_version: "0.1.0rc1"
ezmd_version: "0.1.0rc1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 514
tokens: {o200k_base: 2317, cl100k_base: 2316, claude_approx: 2502}
content_hash: "sha256:ae31a7081eb2249da8e676400a3eed06feb21d45c7fa0f29d022542d2b826718"
source_hash: "sha256:60f5c18eed4c1e9e2e4160d2bc57ad0627a5a5e412bf5836ea9510b4d45d2fee"
truncated: false
warnings: []
injection_risk: none
extra: {anchors_expanded: true, documents: 3, encoding: utf-8, format: YAML}
---
> Sections: 1 Schema, 2 Data, 3 Source. 14 tables.

## Contents

- [1 Schema](#sec-1)
- [2 Data](#sec-2)
    - [2.1 Document 1](#sec-2-1)
        - [2.1.1 metadata](#sec-2-1-1)
            - [2.1.1.1 labels](#sec-2-1-1-1)
        - [2.1.2 data](#sec-2-1-2)
    - [2.2 Document 2](#sec-2-2)
        - [2.2.1 metadata](#sec-2-2-1)
            - [2.2.1.1 labels](#sec-2-2-1-1)
        - [2.2.2 spec](#sec-2-2-2)
            - [2.2.2.1 selector](#sec-2-2-2-1)
                - [2.2.2.1.1 matchLabels](#sec-2-2-2-1-1)
            - [2.2.2.2 template](#sec-2-2-2-2)
                - [2.2.2.2.1 metadata](#sec-2-2-2-2-1)
                - [2.2.2.2.2 spec](#sec-2-2-2-2-2)
    - [2.3 Document 3](#sec-2-3)
        - [2.3.1 metadata](#sec-2-3-1)
        - [2.3.2 spec](#sec-2-3-2)
            - [2.3.2.1 selector](#sec-2-3-2-1)
            - [2.3.2.2 ports](#sec-2-3-2-2)
- [3 Source](#sec-3)

# input.yaml {#doc}

YAML stream of 3 documents; nesting depth 8.

## 1 Schema {#sec-1}

**Table 1**
Columns: Path, Types, Count, Null %, Examples

| Path | Types | Count | Null % | Examples |
|---|---|---:|---:|---|
| / | array | 1 | 0 |  |
| /* | object | 3 | 0 |  |
| /*/apiVersion | string | 3 | 0 | v1, apps/v1 |
| /*/kind | string | 3 | 0 | ConfigMap, Deployment, Service |
| /*/metadata | object | 3 | 0 |  |
| /*/metadata/name | string | 3 | 0 | web-config, web |
| /*/metadata/labels | object | 2 | 0 |  |
| /*/metadata/labels/app | string | 2 | 0 | web |
| /*/metadata/labels/tier | string | 2 | 0 | frontend |
| /*/data | object | 1 | 0 |  |
| /*/data/LOG_LEVEL | string | 1 | 0 | info |
| /*/data/CACHE_TTL | string | 1 | 0 | 300 |
| /*/spec | object | 2 | 0 |  |
| /*/spec/replicas | integer | 1 | 0 | 3 |
| /*/spec/selector | object | 2 | 0 |  |
| /*/spec/selector/matchLabels | object | 1 | 0 |  |
| /*/spec/selector/matchLabels/app | string | 1 | 0 | web |
| /*/spec/template | object | 1 | 0 |  |
| /*/spec/template/metadata | object | 1 | 0 |  |
| /*/spec/template/metadata/labels | object | 1 | 0 |  |
| /*/spec/template/metadata/labels/app | string | 1 | 0 | web |
| /*/spec/template/spec | object | 1 | 0 |  |
| /*/spec/template/spec/containers | array | 1 | 0 |  |
| /\*/spec/template/spec/containers/\* | object | 1 | 0 |  |
| /\*/spec/template/spec/containers/\*/name | string | 1 | 0 | web |
| /\*/spec/template/spec/containers/\*/image | string | 1 | 0 | registry.example.invalid/web:1.10 |
| /\*/spec/template/spec/containers/\*/ports | array | 1 | 0 |  |
| /\*/spec/template/spec/containers/\*/ports/\* | object | 1 | 0 |  |
| /\*/spec/template/spec/containers/\*/ports/\*/containerPort | integer | 1 | 0 | 8080 |
| /\*/spec/template/spec/containers/\*/resources | object | 1 | 0 |  |
| /\*/spec/template/spec/containers/\*/resources/limits | object | 1 | 0 |  |
| /\*/spec/template/spec/containers/\*/resources/limits/cpu | string | 1 | 0 | 500m |
| /\*/spec/template/spec/containers/\*/resources/limits/memory | string | 1 | 0 | 256Mi |
| /*/spec/selector/app | string | 1 | 0 | web |
| /*/spec/ports | array | 1 | 0 |  |
| /\*/spec/ports/\* | object | 1 | 0 |  |
| /\*/spec/ports/\*/port | integer | 1 | 0 | 80 |
| /\*/spec/ports/\*/targetPort | integer | 1 | 0 | 8080 |

## 2 Data {#sec-2}

### 2.1 Document 1 {#sec-2-1}

**Table 2**

| Key | Value |
|---|---|
| apiVersion | v1 |
| kind | ConfigMap |

#### 2.1.1 metadata {#sec-2-1-1}

**Table 3**

| Key | Value |
|---|---|
| name | web-config |

##### 2.1.1.1 labels {#sec-2-1-1-1}

**Table 4**

| Key | Value |
|---|---|
| app | web |
| tier | frontend |

#### 2.1.2 data {#sec-2-1-2}

**Table 5**

| Key | Value |
|---|---|
| LOG_LEVEL | info |
| CACHE_TTL | 300 |

### 2.2 Document 2 {#sec-2-2}

**Table 6**

| Key | Value |
|---|---|
| apiVersion | apps/v1 |
| kind | Deployment |

#### 2.2.1 metadata {#sec-2-2-1}

**Table 7**

| Key | Value |
|---|---|
| name | web |

##### 2.2.1.1 labels {#sec-2-2-1-1}

**Table 8**

| Key | Value |
|---|---|
| app | web |
| tier | frontend |

#### 2.2.2 spec {#sec-2-2-2}

**Table 9**

| Key | Value |
|---|---|
| replicas | 3 |

##### 2.2.2.1 selector {#sec-2-2-2-1}

###### 2.2.2.1.1 matchLabels {#sec-2-2-2-1-1}

**Table 10**

| Key | Value |
|---|---|
| app | web |

##### 2.2.2.2 template {#sec-2-2-2-2}

###### 2.2.2.2.1 metadata {#sec-2-2-2-2-1}

```json
{
  "labels": {
    "app": "web"
  }
}
```

###### 2.2.2.2.2 spec {#sec-2-2-2-2-2}

```json
{
  "containers": [
    {
      "name": "web",
      "image": "registry.example.invalid/web:1.10",
      "ports": [
        {
          "containerPort": 8080
        }
      ],
      "resources": {
        "limits": {
          "cpu": "500m",
          "memory": "256Mi"
        }
      }
    }
  ]
}
```

### 2.3 Document 3 {#sec-2-3}

**Table 11**

| Key | Value |
|---|---|
| apiVersion | v1 |
| kind | Service |

#### 2.3.1 metadata {#sec-2-3-1}

**Table 12**

| Key | Value |
|---|---|
| name | web |

#### 2.3.2 spec {#sec-2-3-2}

##### 2.3.2.1 selector {#sec-2-3-2-1}

**Table 13**

| Key | Value |
|---|---|
| app | web |

##### 2.3.2.2 ports {#sec-2-3-2-2}

**Table 14**

| port | targetPort |
|---:|---:|
| 80 | 8080 |

## 3 Source {#sec-3}

```yaml
# Three Kubernetes manifests in one stream.
apiVersion: v1
kind: ConfigMap
metadata:
  name: web-config
  labels: &labels
    app: web
    tier: frontend
data:
  LOG_LEVEL: info
  CACHE_TTL: "300"
---
# The deployment reuses the label set through an anchor.
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
  labels:
    app: web
    tier: frontend
spec:
  replicas: 3
  selector:
    matchLabels: &match
      app: web
  template:
    metadata:
      labels: *match
    spec:
      containers:
        - name: web
          image: registry.example.invalid/web:1.10
          ports:
            - containerPort: 8080
          resources:
            limits: {cpu: 500m, memory: 256Mi}
---
apiVersion: v1
kind: Service
metadata:
  name: web
spec:
  selector:
    app: web
  ports:
    - port: 80
      targetPort: 8080
```
