# Cahier des charges du stage de PFE

Projet: Legal AI Platform  
Date: 23 Avril 2026  
Periode de stage: 01 Fevrier 2026 -> 30 Juin 2026

## 1. Contexte

Le projet vise a digitaliser les workflows juridiques (gestion de dossier, analyse documentaire, assistance IA, intake client) afin de reduire les delais de traitement et ameliorer la qualite des analyses.

## 2. Objectif general

Concevoir et livrer une plateforme Legal AI complete, demonstrable en soutenance, couvrant les besoins essentiels d'un cabinet juridique moderne.

## 3. Objectifs specifiques

- Mettre en place un backend robuste (auth, multi-tenant, API metier).
- Fournir un workspace interne (React/TypeScript) pour juristes.
- Fournir un portail client public separe et securise.
- Integrer un pipeline IA documentaire (extraction, chunking, indexation, retrieval, synthese).
- Integrer un assistant IA oriente intentions avec agents specialises.
- Integrer le flux voix (upload/enregistrement, transcription, extraction).

## 4. Perimetre fonctionnel

- Gestion des utilisateurs, clients, dossiers et documents.
- Copilot juridique contextualise avec recherche et workflows agents.
- Pipeline voix et conversion transcript -> consultation.
- Portail client pour soumission et suivi des demandes.

## 5. Exigences non fonctionnelles

- Securite: JWT, controle d'acces, isolation par tenant.
- Performance: operations API fluides et traitements lourds en background.
- Fiabilite: gestion d'erreurs, fallback providers IA, scripts de verification.
- Maintenabilite: architecture modulaire et documentation technique.

## 6. Architecture cible

- Backend: FastAPI + PostgreSQL + MinIO + FAISS.
- Frontend interne: React + TypeScript + Vite.
- Portail client: React + TypeScript + Vite.
- IA: pipeline documentaire, RAG, orchestration copilot, agents metier.


## 7. Livrables attendus

- Code source backend/frontend/portail.
- Documentation technique et rapports d'avancement.
- Scenarios de demonstration et resultats d'evaluation.
- Rapport final PFE et support de soutenance.

## 8. Criteres d'acceptation

Le stage est valide si:
- les flux metier essentiels sont operationnels,
- l'assistant IA fonctionne avec contexte dossier et intents,
- le pipeline documentaire et le pipeline voix sont demonstrables,
- le portail client est separe et fonctionnel,
- la documentation permet une comprehension claire par le jury.

## 9. Conclusion

Ce stage PFE livre une plateforme Legal AI exploitable de bout en bout, avec un niveau de maturite technique avance et une trajectoire claire vers une soutenance solide.
