# ADR 0002: Use MongoDB for Primary Database

## Status

Accepted

## Context

The Aloft application needs to store various types of data including:

- User accounts and authentication data
- Points of Interest (POIs) with geographic coordinates
- Flight routes and session data
- Generated content (stories, audio metadata)
- Rate limiting and session data

The data model is characterized by:

- Geographic data (coordinates, spatial queries)
- Flexible schema (different POI types have different attributes)
- Hierarchical relationships (routes → POIs → content)
- High read-to-write ratio
- Need for geospatial queries

## Decision

We will use **MongoDB** as the primary database.

### Rationale

1. **Geospatial Support**: Native support for geospatial queries and indexes
2. **Flexible Schema**: Document model accommodates varying POI attributes
3. **Performance**: Excellent performance for read-heavy workloads
4. **Natural Data Model**: Documents map well to our hierarchical data structures
5. **Scaling**: Horizontal scaling via sharding when needed
6. **Atlas Integration**: MongoDB Atlas provides managed cloud solution
7. **Async Driver**: Motor provides async MongoDB driver for Python

### Alternatives Considered

- **PostgreSQL with PostGIS**: Excellent geospatial support, but requires rigid schema
- **Redis**: Fast but not suitable for primary data storage, lacks persistence guarantees
- **DynamoDB**: AWS-specific, limited query capabilities, higher cost at scale

## Consequences

### Positive

- Natural fit for geospatial POI queries
- Flexible schema allows easy evolution
- Excellent read performance
- Managed solution via MongoDB Atlas
- Strong async driver support

### Negative

- No ACID transactions across documents (though available within single document)
- Memory-intensive for large datasets
- Limited JOIN capabilities (by design)
- Different query paradigm from SQL databases

## Implementation

MongoDB is accessed via the Motor async driver:
```
motor==3.6.0
```

Database connection is managed in `app/core/db.py` with collections defined in `app/services/*_repository.py`.

## References

- [MongoDB Documentation](https://www.mongodb.com/docs/)
- [Motor Documentation](https://motor.readthedocs.io/)
- [MongoDB Geospatial Queries](https://www.mongodb.com/docs/manual/geospatial-queries/)
