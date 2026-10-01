# refugees_inclusion_hackathon

Repository for the 2026 Data &amp; Innovation for refugees and Inclusion hackathon promoted by UNHCR and UniTrento.

## Problem

<!-- TODO -->

## Workflow pipeline

```txt                                                                                      
    START                                               
      │                                                 
┌─────▼─────┐                  ┌───────┐                
│ Interview ├──Data+opinion────► Cashy ├──┐             
└─────┬─────┘                  └───────┘  │             
      │                                 Score+motivation
      │                                   │             
      │                              ┌────▼──────┐      
      └───────────Scorecard──────────► Judgement │      
                                     │  Process  │      
                                     └────┬──────┘      
                                          │             
                                     ┌────▼─────┐       
                                     │ Operator │       
                                     │  Survey  │       
                                     └────┬─────┘       
                                          │             
                                         END                  
```



### Judgement process architecture

```txt

```

- operatore giudica output cashy
- in base alla comparazione tra scorecard e cashy la UI/UX potrebbe variare con messaggi di warning/pop-ups per portare attensione all'uso di IA e possibili bias
- attivazione della precedente feature aleatoria
- possibile roll-back da survey (per furbetti) 

### Operator survey architecture

- feedback obbligatorio sempre
- EC3 (design docs) aggiornato per chiedere feedback sia nel caso in cui output cashy corretto o errato per assicuersi che l'operatore abbia letto e analizzato effettivamente l'esito => forziamo pensiero critico :)
- una volta completato, il risultato del judgement diventa definitivo

## Prototype

<!-- TODO: add an image of the prototype UI -->

- 3 casi: uno semplice, uno difficile e uno bello ganzo
- mostrare meccanica dei pop-up e meccanismo di attention-detection
- chatbot meta analisi domande esistenziali (ma hai mangiato a colazione?)

## Aknowledgements

- ...
- [asciiflow](https://asciiflow.com)