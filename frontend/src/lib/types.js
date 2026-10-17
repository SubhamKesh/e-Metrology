// Domain types mirror the MaapSetu API contract exactly (see /docs/api-contract.md
// in the backend repo). Do not add fields the API doesn't return — if the UI needs
// something the API doesn't expose yet, that's a backend conversation, not a guess.
export const ROLE_LABEL = {
    owner: "Business / User",
    lmo: "Legal Metrology Officer",
    gatc: "GATC",
    admin: "Super Admin",
};
